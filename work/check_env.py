# check_env.py · เช็กว่าเครื่องพร้อมใช้งาน
# รัน: .venv\Scripts\python.exe check_env.py

import sys                                            # โมดูลข้อมูลของตัว Python เอง

sys.stdout.reconfigure(encoding="utf-8")              # ให้พิมพ์ภาษาไทยได้ทุกหน้าจอบน Windows

print("Python เวอร์ชัน :", sys.version.split()[0])    # เช่น 3.14.8
print("Python ที่ใช้อยู่ :", sys.executable)          # ควรอยู่ใน ...\work\.venv\...

ok = True                                             # ตัวจำว่าผ่านทุกข้อหรือไม่

if sys.version_info < (3, 10):                        # Track 3 ต้องใช้ 3.10 ขึ้นไป (Track 3.pdf หน้า 7)
    print("❌ Python ต่ำกว่า 3.10")
    ok = False
else:
    print("✅ Python 3.10 ขึ้นไป")

if ".venv" not in sys.executable:                     # ตรวจว่ารันจาก .venv ไม่ใช่ Python หลักของเครื่อง
    print("⚠️  ไม่ได้รันจาก .venv (อาจไม่มีแพ็กเกจ) ให้ใช้ .venv\\Scripts\\python.exe")

for name in ["requests", "pandas", "openpyxl"]:       # วนตรวจแพ็กเกจที่ต้องใช้ทีละตัว
    try:
        module = __import__(name)                     # ลอง import ด้วยชื่อที่เป็นข้อความ
        print(f"✅ import {name} ได้ (เวอร์ชัน {module.__version__})")
    except ImportError:                               # import ไม่ได้ = ยังไม่ได้ติดตั้ง
        print(f"❌ import {name} ไม่ได้ → ดู OFFLINE_SETUP.md")
        ok = False

print()                                               # เว้นบรรทัด
print("ผลรวม:", "✅ พร้อมใช้งาน" if ok else "❌ ยังไม่พร้อม")
sys.exit(0 if ok else 1)                              # ส่งรหัสออก 0 = ผ่าน, 1 = ไม่ผ่าน (VS Code task ใช้ดูผล)
