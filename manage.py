#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# تحديد مسار المشروع تلقائياً بناءً على مكان السكريبت
REPO_DIR = Path(__file__).resolve().parent
DATA_FILE = REPO_DIR / "data.json"
PAGES_DIR = REPO_DIR / "pages"


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def pause(msg="\nPress Enter to continue..."):
    input(msg)


def ask_yes_no(prompt: str) -> bool:
    ans = input(f"{prompt} (y/n): ").strip().lower()
    return ans in ("y", "yes", "نعم", "اه", "أيوة")


def slugify_folder(name: str) -> str:
    """تحويل اسم القسم إلى اسم مجلد نظيف وآمن للروابط"""
    clean = name.strip().lower()
    clean = re.sub(r"[\s_]+", "-", clean)
    clean = re.sub(r"[^a-z0-9\-]", "", clean)
    clean = re.sub(r"-+", "-", clean).strip("-")
    if not clean:
        clean = f"cat-{int(time.time())}"
    return clean


def sanitize_filename(raw_name: str) -> str:
    """تنظيف اسم الملف على الموقع وضمان امتداد .html"""
    name = raw_name.strip()
    if name.lower().endswith(".html"):
        name = name[:-5]
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = f"page_{int(time.time())}"
    return f"{name}.html"


def filename_to_display_title(filename_or_name: str) -> str:
    """تحويل Lecture_1_-_intro_to_circuits إلى Lecture 1 - intro to circuits"""
    stem = filename_or_name.strip()
    if stem.lower().endswith(".html"):
        stem = stem[:-5]
    title = stem.replace("_", " ")
    title = re.sub(r"\s+", " ", title).strip()
    return title or "Untitled"


def infer_category_folder(cat: dict) -> str:
    """استخراج اسم مجلد القسم سواء كان مسجلاً أو من روابط العناصر القديمة"""
    if cat.get("folder"):
        return cat["folder"]
    for item in cat.get("items", []):
        url = item.get("url", "")
        parts = url.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "pages":
            return parts[1]
    return slugify_folder(cat.get("id") or cat.get("title") or "general")


def load_data() -> dict:
    if not DATA_FILE.exists():
        default_data = {
            "appTitle": "الأقسام الرئيسية",
            "appSubtitle": "اختر القسم للبدء",
            "categories": [],
        }
        save_data(default_data)
        return default_data

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "categories" not in data or not isinstance(data["categories"], list):
        data["categories"] = []

    # ضمان وجود حقل folder لكل قسم للتوافق مع أي بيانات قديمة
    for cat in data["categories"]:
        if "folder" not in cat:
            cat["folder"] = infer_category_folder(cat)
        if "items" not in cat or not isinstance(cat["items"], list):
            cat["items"] = []

    return data


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def git_sync(commit_message: str):
    """رفع التغييرات تلقائياً إلى GitHub"""
    print("\n⏳ Syncing changes with GitHub...")
    try:
        subprocess.run(["git", "add", "-A"], cwd=REPO_DIR, check=True)
        diff_check = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR
        )
        if diff_check.returncode == 0:
            print("ℹ️  No file changes detected to commit.")
            return

        subprocess.run(
            ["git", "commit", "-m", commit_message], cwd=REPO_DIR, check=True
        )
        subprocess.run(["git", "push"], cwd=REPO_DIR, check=True)
        print("✅ Successfully updated and pushed to GitHub!")
    except subprocess.CalledProcessError as e:
        print(f"\n⚠️  Git operation failed (exit code {e.returncode}).")
        print("Changes are saved locally. Check your internet connection and run 'git push' later.")


def prompt_local_html_file() -> Path | None:
    """طلب مسار ملف HTML من الجهاز والتحقق من وجوده"""
    while True:
        raw = input("\nEnter local HTML file path (or 0 to cancel): ").strip()
        if raw == "0":
            return None
        # إزالة علامات التنصيص إذا تم لصق المسار من مدير الملفات
        if (raw.startswith('"') and raw.endswith('"')) or (
            raw.startswith("'") and raw.endswith("'")
        ):
            raw = raw[1:-1].strip()

        if not raw:
            continue

        file_path = Path(os.path.expanduser(raw))
        if not file_path.is_absolute():
            file_path = (Path.cwd() / file_path).resolve()

        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            continue
        if not file_path.is_file():
            print(f"❌ Path is not a file: {file_path}")
            continue

        return file_path


def select_from_list(title: str, options: list[str]) -> int | None:
    """عرض قائمة مرقمة وإرجاع index العنصر المختار أو None عند الإلغاء"""
    print(f"\n--- {title} ---")
    for idx, label in enumerate(options, start=1):
        print(f"{idx}. {label}")
    print("0. Back / Cancel")

    while True:
        choice = input("\nChoose number: ").strip()
        if choice == "0":
            return None
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(options):
                return num - 1
        print("❌ Invalid choice. Enter a valid number from the list.")


# ==========================================
# عمليات الملفات داخل Category
# ==========================================
def handle_add_file(data: dict, category: dict):
    src_file = prompt_local_html_file()
    if not src_file:
        print("Cancelled.")
        return

    raw_site_name = input(
        "\nEnter file name for the site (e.g. Lecture_1_-_intro_to_circuits): "
    ).strip()
    if not raw_site_name:
        print("❌ Name cannot be empty. Cancelled.")
        return

    target_filename = sanitize_filename(raw_site_name)
    display_title = filename_to_display_title(target_filename)
    cat_folder = infer_category_folder(category)
    dest_dir = PAGES_DIR / cat_folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / target_filename
    rel_url = f"pages/{cat_folder}/{target_filename}"

    print(f"\n📄 Site Display Title : {display_title}")
    print(f"🔗 Target Repo Path   : {rel_url}")

    existing_item = next(
        (it for it in category["items"] if it.get("url") == rel_url), None
    )
    if dest_file.exists() or existing_item:
        if not ask_yes_no("⚠️  A file with this name already exists in this category. Overwrite?"):
            print("Cancelled.")
            return

    shutil.copy2(src_file, dest_file)

    if existing_item:
        existing_item["title"] = display_title
    else:
        category["items"].append(
            {
                "id": f"item-{int(time.time() * 1000)}",
                "title": display_title,
                "subtitle": "",
                "tag": "",
                "icon": "📄",
                "url": rel_url,
            }
        )

    save_data(data)
    git_sync(f"Add file '{display_title}' to '{category['title']}'")


def handle_edit_file(data: dict, category: dict):
    items = category.get("items", [])
    if not items:
        print("\nℹ️  No files in this category to edit.")
        return

    labels = [
        f"{it.get('title', 'Untitled')}  [{Path(it.get('url', '')).name}]"
        for it in items
    ]
    idx = select_from_list(f"Edit File in '{category['title']}'", labels)
    if idx is None:
        return

    selected_item = items[idx]
    item_title = selected_item.get("title", "Untitled")
    rel_url = selected_item.get("url", "")

    if not ask_yes_no(f"Are you sure you want to edit '{item_title}'?"):
        print("Cancelled.")
        return

    new_src_file = prompt_local_html_file()
    if not new_src_file:
        print("Cancelled.")
        return

    dest_file = REPO_DIR / rel_url
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(new_src_file, dest_file)

    save_data(data)
    git_sync(f"Edit file '{item_title}' in '{category['title']}'")


def handle_delete_file(data: dict, category: dict):
    items = category.get("items", [])
    if not items:
        print("\nℹ️  No files in this category to delete.")
        return

    labels = [
        f"{it.get('title', 'Untitled')}  [{Path(it.get('url', '')).name}]"
        for it in items
    ]
    idx = select_from_list(f"Delete File from '{category['title']}'", labels)
    if idx is None:
        return

    selected_item = items[idx]
    item_title = selected_item.get("title", "Untitled")
    rel_url = selected_item.get("url", "")

    if not ask_yes_no(f"Are you sure you want to delete '{item_title}'?"):
        print("Cancelled.")
        return

    target_file = REPO_DIR / rel_url
    if target_file.exists() and target_file.is_file():
        target_file.unlink()

    items.pop(idx)
    save_data(data)
    git_sync(f"Delete file '{item_title}' from '{category['title']}'")


# ==========================================
# القائمة الرئيسية والـ Categories
# ==========================================
def menu_open_categories():
    data = load_data()
    categories = data.get("categories", [])
    if not categories:
        print("\nℹ️  No categories found. Use 'Add Category' first.")
        pause()
        return

    labels = [
        f"{cat.get('title', 'Untitled')} ({len(cat.get('items', []))} files)"
        for cat in categories
    ]
    cat_idx = select_from_list("Open Categories", labels)
    if cat_idx is None:
        return

    while True:
        data = load_data()
        if cat_idx >= len(data["categories"]):
            break
        category = data["categories"][cat_idx]

        print(f"\n===============================")
        print(f"📁 Category: {category['title']}")
        print(f"===============================")
        print("1. Edit File")
        print("2. Add File")
        print("3. Delete File")
        print("0. Back to Main Menu")

        choice = input("\nChoose option: ").strip()
        if choice == "1":
            handle_edit_file(data, category)
            pause()
        elif choice == "2":
            handle_add_file(data, category)
            pause()
        elif choice == "3":
            handle_delete_file(data, category)
            pause()
        elif choice == "0":
            break
        else:
            print("❌ Invalid choice.")


def menu_add_category():
    data = load_data()
    raw_name = input("\nEnter new category name: ").strip()
    if not raw_name:
        print("❌ Category name cannot be empty.")
        pause()
        return

    display_title = filename_to_display_title(raw_name)
    base_slug = slugify_folder(raw_name)

    existing_folders = {infer_category_folder(c) for c in data["categories"]}
    folder_slug = base_slug
    counter = 2
    while folder_slug in existing_folders:
        folder_slug = f"{base_slug}-{counter}"
        counter += 1

    print(f"\n📁 Category Display Name : {display_title}")
    print(f"📂 GitHub Folder Path    : pages/{folder_slug}/")

    if not ask_yes_no(f"Confirm creating category '{display_title}'?"):
        print("Cancelled.")
        pause()
        return

    cat_dir = PAGES_DIR / folder_slug
    cat_dir.mkdir(parents=True, exist_ok=True)
    # ملف .gitkeep ضروري حتى يتعرف Git على المجلد الفارغ ويرفعه لـ GitHub
    (cat_dir / ".gitkeep").touch()

    data["categories"].append(
        {
            "id": folder_slug,
            "folder": folder_slug,
            "title": display_title,
            "description": "",
            "icon": "📘",
            "items": [],
        }
    )

    save_data(data)
    git_sync(f"Add category '{display_title}'")
    pause()


def menu_delete_category():
    data = load_data()
    categories = data.get("categories", [])
    if not categories:
        print("\nℹ️  No categories available to delete.")
        pause()
        return

    labels = [
        f"{cat.get('title', 'Untitled')} ({len(cat.get('items', []))} files)"
        for cat in categories
    ]
    idx = select_from_list("Delete Category", labels)
    if idx is None:
        return

    target_cat = categories[idx]
    cat_title = target_cat.get("title", "Untitled")
    files_count = len(target_cat.get("items", []))
    cat_folder = infer_category_folder(target_cat)

    print(f"\n⚠️  Selected category: '{cat_title}' ({files_count} files)")

    # تأكيد الحذف 3 مرات متتالية
    if not ask_yes_no(f"[Confirmation 1/3] Are you sure you want to delete '{cat_title}'?"):
        print("❌ Operation cancelled.")
        pause()
        return

    if not ask_yes_no(
        f"[Confirmation 2/3] This will permanently delete '{cat_title}' and ALL ({files_count}) files inside it. Continue?"
    ):
        print("❌ Operation cancelled.")
        pause()
        return

    if not ask_yes_no(
        f"[Confirmation 3/3] Final confirmation: Delete '{cat_title}' permanently?"
    ):
        print("❌ Operation cancelled.")
        pause()
        return

    folder_path = PAGES_DIR / cat_folder
    if folder_path.exists() and folder_path.is_dir():
        shutil.rmtree(folder_path)

    categories.pop(idx)
    save_data(data)
    git_sync(f"Delete category '{cat_title}'")
    pause()


def main():
    if not (REPO_DIR / ".git").exists():
        print(f"❌ Error: '{REPO_DIR}' is not a git repository.")
        sys.exit(1)

    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        clear_screen()
        print("====================================")
        print("   🚀 Site Content Manager CLI")
        print("====================================")
        print("1. Open Categories")
        print("2. Add Category")
        print("3. Delete Category")
        print("4. Exit")

        choice = input("\nSelect an option (1-4): ").strip()
        if choice == "1":
            menu_open_categories()
        elif choice == "2":
            menu_add_category()
        elif choice == "3":
            menu_delete_category()
        elif choice == "4":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1, 2, 3, or 4.")
            time.sleep(0.8)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Exited.")
