"""CPU contract tests with a deterministic, input-dependent tiny ONNX model."""
import builtins
import ast
import csv
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw

TEAM = Path(__file__).resolve().parents[1]/'team_XX_day1'
sys.path.insert(0,str(TEAM))
import infer


def test_infer_python39_compatibility():
    source = (TEAM/'infer.py').read_text(encoding='utf-8')
    tree = ast.parse(source, filename='infer.py', feature_version=(3, 9))
    imports = {alias.name.split('.')[0] for node in ast.walk(tree)
               if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module.split('.')[0] for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module)
    # Explicit allowlist also rejects newer stdlib imports such as tomllib.
    assert imports <= {'__future__', 'dataclasses', 'pathlib', 'cv2', 'numpy', 'PIL',
                       'json', 'sys', 'onnxruntime', 'csv', 'shutil', 'argparse'}
    assert any(isinstance(node, ast.ImportFrom) and node.module == '__future__' and
               any(alias.name == 'annotations' for alias in node.names) for node in tree.body)


@pytest.fixture(scope='session')
def weights(tmp_path_factory):
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    root=tmp_path_factory.mktemp('model')
    w=np.array([[1.,-.4,.2,0,.1,-.2,.3],[-.2,1.,.3,0,.1,.2,-.3],[.1,-.2,1.,.2,0,.3,-.1]],np.float32)
    nodes=[helper.make_node('GlobalAveragePool',['images'],['pooled']),
           helper.make_node('Flatten',['pooled'],['flat'],axis=1),
           helper.make_node('MatMul',['flat','w'],['logits'])]
    graph=helper.make_graph(nodes,'input-dependent-test-model',
        [helper.make_tensor_value_info('images',TensorProto.FLOAT,['N',3,160,160])],
        [helper.make_tensor_value_info('logits',TensorProto.FLOAT,['N',7])],
        [numpy_helper.from_array(w,name='w')])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)])
    model.ir_version=8
    onnx.save(model,str(root/'best.onnx'))
    (root/'meta.json').write_text(json.dumps({'classes':list(infer.CLASSES),'input_size':160}))
    return root/'best.onnx'


@pytest.fixture
def photo(tmp_path):
    path=tmp_path/'source'/'bean.JPG';path.parent.mkdir()
    im=Image.new('RGB',(480,640),(240,240,240));d=ImageDraw.Draw(im)
    for x,y in [(140,190),(260,190),(140,310),(260,310)]:
        d.ellipse((x,y,x+48,y+65),fill=(105,65,25))
    im.save(path,quality=95)
    return path


def cli(tmp_path,source,weights,*flags,aliases=False):
    out=tmp_path/'outputs'
    cmd=[sys.executable,str(TEAM/'infer.py'),'--input',str(source),
        '--weight' if aliases else '--weights',str(weights),
        '--output' if aliases else '--out',str(out),'--device','cpu','--quick',*flags]
    result=subprocess.run(cmd,text=True,capture_output=True,timeout=60)
    return result,out


def test_single_uppercase_alias_and_content_detection(tmp_path,photo,weights):
    before=hashlib.sha256(photo.read_bytes()).hexdigest()
    renamed=weights.parent/'renamed.pt';shutil.copy2(weights,renamed)
    result,out=cli(tmp_path,photo,renamed,aliases=True)
    assert result.returncode==0,result.stderr
    rows=infer.validate_csv(out/'predictions.csv',[photo.name])
    assert all((out/c).is_dir() for c in infer.CLASSES)
    assert (out/rows[0]['class']/photo.name).read_bytes()==photo.read_bytes()
    assert before==hashlib.sha256(photo.read_bytes()).hexdigest()
    assert not (out/'_debug').exists()


def test_sorted_directory_and_default_no_assignment(tmp_path,photo,weights):
    for i in range(6): shutil.copy2(photo,photo.parent/f'{i}.png')
    result,out=cli(tmp_path,photo.parent,weights)
    assert result.returncode==0,result.stderr
    rows=infer.validate_csv(out/'predictions.csv',sorted(p.name for p in photo.parent.iterdir()))
    assert len({r['class'] for r in rows})==1  # default must not force unique classes


def test_missing_weight_fallback_and_debug(tmp_path,photo,weights):
    result,out=cli(tmp_path,photo,weights.parent/'missing.pt','--debug')
    assert result.returncode==0,result.stderr
    assert 'using' in result.stderr and 'best.onnx' in result.stderr
    assert list((out/'_debug').glob('*.png'))


@pytest.mark.parametrize('case',['empty','unreadable','missing_input','missing_weights',
                                 'duplicate','inside','equal','invalid_weights','assignment_count'])
def test_error_paths(tmp_path,photo,weights,case):
    source=photo; flags=[]
    if case=='empty': source=tmp_path/'empty';source.mkdir()
    if case=='unreadable': photo.write_bytes(b'not an image')
    if case=='missing_input': source=tmp_path/'missing.jpg'
    if case=='missing_weights': weights=tmp_path/'absent'/'best.onnx'
    if case=='invalid_weights': weights=tmp_path/'bad.onnx';weights.write_text('invalid graph')
    if case=='duplicate':
        folder=photo.parent/'nested';folder.mkdir();shutil.copy2(photo,folder/photo.name);source=photo.parent
    if case in ['inside','equal']:
        source=photo.parent;flags=['--out',str(source/'out' if case=='inside' else source)]
    if case=='assignment_count': flags=['--assume-one-per-class']
    result,_=cli(tmp_path,source,weights,*flags)
    assert result.returncode!=0
    assert 'Error:' in result.stderr


def test_exif_rotation_is_correct_and_prediction_stable(tmp_path,photo,weights):
    # Lossless PNG preserves exact pixels while EXIF tests orientation order.
    with Image.open(photo) as im: original=im.convert('RGB')
    upright=tmp_path/'upright.png';original.save(upright)
    rotated=original.transpose(Image.Transpose.ROTATE_90)
    exif=Image.Exif();exif[274]=6
    turned=tmp_path/'turned.png';rotated.save(turned,exif=exif)
    np.testing.assert_array_equal(infer.decode_image(upright),infer.decode_image(turned))
    model=infer.load_model(weights)
    a=infer.predict_image(model,upright);b=infer.predict_image(model,turned)
    np.testing.assert_array_equal(a,b)
    assert a.argmax()==b.argmax()


def test_opencv_import_fallback_matches_ort(monkeypatch,photo,weights):
    primary=infer.load_model(weights)
    original_import=builtins.__import__
    def fail_ort(name,*args,**kwargs):
        if name=='onnxruntime': raise ImportError('test unavailable runtime')
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',fail_ort)
    fallback=infer.load_model(weights)
    assert fallback.backend=='opencv'
    np.testing.assert_allclose(infer.predict_image(primary,photo),
                               infer.predict_image(fallback,photo),atol=1e-3,rtol=0)


def test_hungarian_optimality():
    scores=np.random.default_rng(19).normal(size=(7,7))
    result=infer.assign_one_per_class(scores)
    expected=max(sum(scores[i,p[i]] for i in range(7)) for p in itertools.permutations(range(7)))
    assert len(set(result))==7
    assert sum(scores[i,result[i]] for i in range(7))==pytest.approx(expected)


def test_explicit_assignment(tmp_path,photo,weights):
    for i in range(6): shutil.copy2(photo,photo.parent/f'{i}.JPG')
    result,out=cli(tmp_path,photo.parent,weights,'--assume-one-per-class')
    assert result.returncode==0,result.stderr
    with (out/'predictions.csv').open() as f: rows=list(csv.DictReader(f))
    assert {r['class'] for r in rows}==set(infer.CLASSES)


@pytest.mark.parametrize('content',[
    'class,filename\ngood,a.jpg\n',
    'filename,class\na.jpg,Good\n',
    'filename,class\n/a.jpg,good\n',
    'filename,class\na.jpg,good\na.jpg,good\n',
    'filename,class\n',
    'filename,class\na.jpg,good,extra\n',
])
def test_csv_rejects_invalid(tmp_path,content):
    path=tmp_path/'bad.csv';path.write_text(content)
    with pytest.raises(ValueError,match='CSV validation failed'):
        infer.validate_csv(path,['a.jpg'])


def test_failing_csv_validation_exits_nonzero(monkeypatch,tmp_path,photo,weights,capsys):
    def reject(*args): raise ValueError('CSV validation failed: injected corruption')
    monkeypatch.setattr(infer,'validate_csv',reject)
    code=infer.main(['--input',str(photo),'--weights',str(weights),'--out',str(tmp_path/'out')])
    assert code!=0 and 'CSV validation failed' in capsys.readouterr().err
    assert not (tmp_path/'out'/'predictions.csv').exists()


def test_model_is_deterministic_and_input_dependent(weights):
    model=infer.load_model(weights)
    x=np.zeros((2,3,160,160),np.float32);x[1,0]=1
    a=model.logits(x);b=model.logits(x)
    np.testing.assert_array_equal(a,b)
    assert not np.allclose(a[0],a[1])


def test_both_patch_sources_and_square_scale(photo):
    patches,kinds,boxes,seg=infer.extract_patches(infer.decode_image(photo))
    assert set(kinds)=={'instance','window'}
    assert patches.shape[1:]==(160,160,3)
    sizes=[box[2] for box,kind in zip(boxes,kinds) if kind=='instance']
    assert len(set(sizes))==1
    assert all(w==h for x,y,w,h in boxes)
