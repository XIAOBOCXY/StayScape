from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILLS = [
    "yusuchengjing-hotel-ops",
    "stayscape-product-generator",
    "stayscape-visitor-matcher",
    "stayscape-marketing-writer",
    "stayscape-clawhive-chat",
]
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt"}
SENSITIVE_NAMES = {"credentials.json", "secrets.json", "service-account.json"}
SECRET_ASSIGNMENT = re.compile(r"(?im)^\s*(?:api[_-]?key|secret|access[_-]?token|password)\s*[:=]\s*['\"]?(?!your[-_ ]|change[-_ ]|example|placeholder|none|null)[^\s'\"]{8,}")


def validate_skill(path: Path) -> None:
    skill_file = path / "SKILL.md"
    if not skill_file.is_file():
        raise RuntimeError(f"missing {skill_file}")
    text = skill_file.read_text(encoding="utf-8")
    # OpenClaw skill frontmatter is identity metadata.  Tool permissions are
    # enforced by the Gateway tool policy/plugin configuration, not by a
    # non-standard `allowed-tools` line in SKILL.md.
    for field in ("name:", "description:"):
        if field not in text.split("---", 2)[1]:
            raise RuntimeError(f"missing frontmatter field {field}")
    name = re.search(r"^name:\s*([^\n]+)", text, re.MULTILINE).group(1).strip()
    if name != path.name or not re.fullmatch(r"[a-z0-9-]+", name):
        raise RuntimeError(f"invalid skill name: {name}")


def safe_files(source: Path):
    for file in sorted(source.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(source)
        parts = {part.lower() for part in relative.parts}
        filename = file.name.lower()
        if parts & {"__pycache__", "node_modules", ".venv", ".git", ".codex"}:
            continue
        if filename == ".env" or (filename.startswith(".env.") and filename != ".env.example"):
            continue
        if filename in SENSITIVE_NAMES or file.suffix.lower() in SENSITIVE_SUFFIXES:
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            text = ""
        if "-----BEGIN " in text and "PRIVATE KEY-----" in text:
            raise RuntimeError(f"private key material found in {relative}")
        if SECRET_ASSIGNMENT.search(text):
            raise RuntimeError(f"possible secret assignment found in {relative}; use environment variables")
        yield file


def package(name: str) -> Path:
    source = ROOT / "skills" / name
    validate_skill(source)
    output_dir = ROOT / "dist"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"{name}.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in safe_files(source):
            archive.write(file, file.relative_to(source).as_posix())
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        if "SKILL.md" not in names:
            raise RuntimeError(f"SKILL.md is not at ZIP root: {output}")
        if output.stat().st_size >= 50 * 1024 * 1024:
            raise RuntimeError(f"skill ZIP is too large: {output}")
    return output


if __name__ == "__main__":
    built: list[Path] = []
    for skill in SKILLS:
        built.append(package(skill))
    # A single archive that carries every Skill plus the usage note, for
    # handing the whole set to a platform that accepts one upload.
    output_dir = ROOT / "dist"
    bundle = output_dir / "stayscape-skills-bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in built:
            archive.write(item, f"skills/{item.name}")
        readme = output_dir / "SKILLS-README.md"
        readme.write_text(
            "# StayScape Skill 包\n\n"
            "每个 zip 的根目录都包含 SKILL.md，可单独上传到 ClawHive / SkillHub。\n\n"
            "- yusuchengjing-hotel-ops：酒店临期库存运营总控（含产品生成、游客匹配、营销文案三种工作模式）\n"
            "- stayscape-product-generator：产品候选生成与校验\n"
            "- stayscape-visitor-matcher：游客咨询与推荐匹配\n"
            "- stayscape-marketing-writer：营销素材文案\n\n"
            "- stayscape-clawhive-chat：ClawHive 游客/运营自然语言入口，可查询产品并生成待确认候选\n\n"
            "上传后在 Agent 中启用对应 Skill，并通过 stayscape-openclaw-plugin 调用平台工具。\n",
            encoding="utf-8",
        )
        archive.write(readme, "SKILLS-README.md")
    for item in [*built, bundle]:
        print(item)
