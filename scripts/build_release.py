"""Validate metadata and produce a manual-install ZIP without credentials."""
from pathlib import Path
import json
import zipfile
root = Path(__file__).resolve().parents[1]
component = root / 'custom_components/roborock_z1_monitor'
manifest = json.loads((component/'manifest.json').read_text(encoding='utf-8'))
assert manifest['domain'] == component.name
assert manifest['requirements'] == ['python-roborock==4.8.0']
assert manifest['codeowners'] and manifest['issue_tracker']
assert json.loads((root/'hacs.json').read_text(encoding='utf-8'))['name']
out = root/'dist'
out.mkdir(exist_ok=True)
files = [p for p in component.rglob('*') if p.is_file() and p.suffix in ('.py','.json','.png')]
for p in files:
    if p.suffix == '.py': compile(p.read_text(encoding='utf-8'),str(p),'exec')
    if p.suffix == '.json': json.loads(p.read_text(encoding='utf-8'))
with zipfile.ZipFile(out/'roborock_z1_monitor.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for p in files + [root/'LICENSE',root/'README.md',root/'A204_TESTING.md']:
        archive.write(p,p.relative_to(root).as_posix())
print(f"Version {manifest['version']}: {len(files)} component files; ZIP ready")
