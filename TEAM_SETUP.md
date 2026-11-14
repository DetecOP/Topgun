# คู่มือเพิ่มคอมพิวเตอร์เครื่องใหม่เข้าทีม

ทำตามขั้นตอนนี้ครั้งเดียวในคอมพิวเตอร์แต่ละเครื่อง

## 1. ติดตั้ง Git

- **Windows:** `winget install --id Git.Git -e` หรือดาวน์โหลดจาก https://git-scm.com/download/win
- **macOS:** `brew install git` หรือ `xcode-select --install`
- **Linux (Debian/Ubuntu):** `sudo apt install git`

ตรวจสอบ: `git --version` (ถ้าแสดงเลขเวอร์ชันแปลว่าติดตั้งสำเร็จ)

## 2. ตั้งค่าตัวตนใน Git

ชื่อและอีเมลนี้จะแสดงในทุก Commit ที่คุณสร้าง

```bash
git config --global user.name "ชื่อของคุณ"
git config --global user.email "อีเมล-noreply-ของ-GitHub"
git config --global init.defaultBranch main   # ให้ Branch เริ่มต้นชื่อ main
git config --global pull.rebase false         # ให้ git pull ใช้วิธี merge
```

ถ้าไม่อยากเปิดเผยอีเมลจริง ให้ใช้อีเมล noreply ของ GitHub ดูได้ที่ GitHub → Settings → Emails หน้าตาประมาณ `12345678+username@users.noreply.github.com`

## 3. ติดตั้ง GitHub CLI และล็อกอิน

- **Windows:** `winget install --id GitHub.cli -e`
- **macOS:** `brew install gh`
- **Linux:** ดูที่ https://github.com/cli/cli/blob/trunk/docs/install_linux.md

```bash
gh auth login
```

เลือก **GitHub.com → HTTPS → Yes (authenticate Git) → Login with a web browser** แล้วล็อกอินในเบราว์เซอร์
**ห้าม** วางรหัสผ่านหรือโทเคนลงในแชต สคริปต์ หรือไฟล์ใด ๆ

ตรวจสอบ: `gh auth status`

## 4. ตอบรับคำเชิญ

เจ้าของโปรเจกต์จะเชิญบัญชี GitHub ของคุณ ให้กดตอบรับจากอีเมล หรือที่ https://github.com/notifications
ถ้ายังไม่ตอบรับ จะ Clone Repository แบบ private ไม่ได้

## 5. Clone Repository

```bash
gh repo clone DetecOP/team-project   # ดาวน์โหลดโปรเจกต์
cd team-project                      # เข้าโฟลเดอร์โปรเจกต์
git checkout develop                 # สลับไป Branch develop
git pull origin develop              # ดึงงานล่าสุด
```

## 6. ตั้งค่าโปรเจกต์ครั้งแรก

```bash
cp .env.example .env      # Windows PowerShell: Copy-Item .env.example .env
```

ใส่ค่าของเครื่องตัวเองในไฟล์ `.env` (ไฟล์นี้จะไม่ถูกอัปโหลดขึ้น GitHub) แล้วติดตั้ง dependency ตามที่ระบุใน README.md

## 7. การทำงานประจำวัน: Pull และ Push

เริ่มงานใหม่:

```bash
git checkout develop
git pull origin develop                # ดึงงานล่าสุดของทีม
git checkout -b feature/your-task      # สร้าง Branch ของงานนี้
```

บันทึกและอัปโหลดงาน:

```bash
git status                             # ดูว่าแก้ไฟล์อะไรไปบ้าง
git add <ไฟล์>                         # เลือกไฟล์ (ระวัง "git add ." ให้ตรวจ git status ก่อน)
git commit -m "feat: อธิบายสิ่งที่เปลี่ยน"   # บันทึก Commit
git push -u origin feature/your-task   # อัปโหลดขึ้น GitHub
```

เปิด Pull Request เข้า `develop`:

```bash
gh pr create --base develop
```

นำงานของคนอื่นเข้ามาใน Branch ของเรา:

```bash
git checkout develop
git pull origin develop
git checkout feature/your-task
git merge develop
```

## การแก้ปัญหาที่พบบ่อย

| ปัญหา | วิธีแก้ |
|---|---|
| `Permission denied` / `Repository not found` | ตอบรับคำเชิญก่อน แล้วรัน `gh auth status` และ `gh auth setup-git` |
| Push แล้วขึ้น `rejected ... (fetch first)` | รัน `git pull` ก่อน แก้ conflict แล้ว Push ใหม่ **ห้าม** ใช้ `--force` |
| Merge conflict | แก้ไฟล์ที่มีเครื่องหมาย `<<<<<<<` ให้เรียบร้อย แล้ว `git add <ไฟล์>` และ `git commit` |
| Commit ผิด Branch (ยังไม่ได้ Push) | `git branch feature/new-name` แล้ว `git reset --soft HEAD~1` บน Branch ที่ผิด ถ้าไม่แน่ใจให้ถามทีมก่อน |
| `0x80072f0d` / `SEC_E_UNTRUSTED_ROOT` / ใบรับรองไม่น่าเชื่อถือบน Windows | ตรวจนาฬิกาเครื่องให้ถูกต้อง และปิดการสแกน HTTPS ของแอนติไวรัสหรือพร็อกซีสำหรับ `github.com` และ `*.githubusercontent.com` |
