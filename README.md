# Topgun

โปรเจกต์ที่ทีมใช้ทำงานร่วมกัน "จะกาแฟหรือจะแกฟะ"

## Repository (ที่เก็บโค้ดบน GitHub)

```
https://github.com/DetecOP/Topgun
```


## Branch (สายงานของโค้ด)

| Branch      | ใช้ทำอะไร                                                        |
|-------------|------------------------------------------------------------------|
| `main`      | โค้ดเวอร์ชันเสถียร รับเฉพาะงานที่ผ่านการรีวิวผ่าน Pull Request แล้ว |
| `develop`   | Branch พัฒนาร่วมกันของทีม งานใหม่ทุกชิ้นรวมเข้าที่นี่ก่อน            |
| `feature/*` | หนึ่ง Branch ต่อหนึ่งฟีเจอร์หรือหนึ่งงาน เช่น `feature/login-page`   |
| `fix/*`     | แก้บั๊ก เช่น `fix/crash-on-startup`                               |

## การติดตั้ง

1. ติดตั้ง Git: https://git-scm.com/downloads
2. ติดตั้ง GitHub CLI: https://cli.github.com
3. ล็อกอิน: `gh auth login` (เลือก **GitHub.com → HTTPS → Login with a web browser**)
4. Clone โปรเจกต์ (ดูหัวข้อถัดไป)
5. คัดลอก `.env.example` เป็น `.env` แล้วใส่ค่าของเครื่องตัวเอง

ใช้คอมพิวเตอร์เครื่องใหม่? ทำตาม [TEAM_SETUP.md](TEAM_SETUP.md)

## Clone (ดาวน์โหลด) Repository

```bash
gh repo clone DetecOP/Topgun   # ดาวน์โหลดโปรเจกต์ลงเครื่อง
cd Topgun                      # เข้าไปในโฟลเดอร์โปรเจกต์
git checkout develop                 # สลับไปที่ Branch develop
```

## Sync (อัปเดต) งานล่าสุด

ทำทุกครั้งก่อนเริ่มงานแต่ละวัน:

```bash
git checkout develop        # สลับไป develop
git pull origin develop     # ดึงงานล่าสุดของทีมจาก GitHub
```

จากนั้นนำงานล่าสุดเข้ามาใน Branch ของตัวเอง:

```bash
git checkout feature/your-branch
git merge develop           # รวมงานล่าสุดจาก develop เข้า Branch ของเรา
```

## การส่งโค้ด (Contribute)

```bash
git checkout develop
git pull origin develop
git checkout -b feature/short-description   # สร้าง Branch ใหม่สำหรับงานนี้
# ...แก้ไขโค้ด...
git status                                  # ตรวจว่าแก้ไฟล์อะไรไปบ้าง
git add <ไฟล์>                              # เลือกไฟล์ที่จะบันทึก
git commit -m "feat: อธิบายสิ่งที่เปลี่ยน"      # บันทึก (Commit) การเปลี่ยนแปลง
git push -u origin feature/short-description # อัปโหลด (Push) ขึ้น GitHub
gh pr create --base develop                 # เปิด Pull Request เข้า develop
```

อ่านขั้นตอนการทำงาน กฎการตั้งชื่อ และการรีวิวโค้ดทั้งหมดได้ที่ [CONTRIBUTING.md](CONTRIBUTING.md)

## คำศัพท์ที่ควรรู้

| คำ | ความหมาย |
|---|---|
| Repository | ที่เก็บโค้ดพร้อมประวัติการแก้ไขทั้งหมด |
| Branch | สายงานแยก ทำงานได้โดยไม่กระทบงานของคนอื่น |
| Commit | การบันทึกการเปลี่ยนแปลงหนึ่งครั้ง พร้อมข้อความอธิบาย |
| Push | อัปโหลด Commit จากเครื่องเราขึ้น GitHub |
| Pull | ดาวน์โหลด Commit ใหม่จาก GitHub ลงเครื่องเรา |
| Pull Request (PR) | คำขอให้ทีมรีวิวและรวมงานใน Branch ของเราเข้า Branch หลัก |
