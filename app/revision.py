"""Read build metadata without shipping Git configuration or history in the image."""
import json
import re
from pathlib import Path


def source_revision(root):
    root = Path(root)
    git_dir = root / '.git'
    # A metadata-only Docker build stage copies the contents of .git into root.
    if not git_dir.exists():
        git_dir = root
    elif git_dir.is_file():
        value = git_dir.read_text().strip()
        if not value.startswith('gitdir: '):
            return {'branch': 'unknown', 'revision': 'unknown'}
        git_dir = (root / value[8:]).resolve()
    try:
        head = (git_dir / 'HEAD').read_text().strip()
        branch = 'detached'
        if head.startswith('ref: '):
            ref = head[5:]
            if not ref.startswith('refs/heads/') or '..' in Path(ref).parts:
                return {'branch': 'unknown', 'revision': 'unknown'}
            branch = ref[len('refs/heads/'):]
            common = git_dir
            if (git_dir / 'commondir').exists():
                common = (git_dir / (git_dir / 'commondir').read_text().strip()).resolve()
            loose = common / ref
            if loose.exists():
                head = loose.read_text().strip()
            else:
                head = next((line.split()[0] for line in (common / 'packed-refs').read_text().splitlines()
                             if line and not line.startswith(('#','^')) and line.split()[-1] == ref), '')
        if not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', head) or not branch:
            return {'branch': 'unknown', 'revision': 'unknown'}
        return {'branch': branch, 'revision': head.lower()}
    except (OSError, ValueError):
        return {'branch': 'unknown', 'revision': 'unknown'}


def build_revision():
    file = Path(__file__).with_name('build_revision.json')
    if file.exists():
        try:
            data = json.loads(file.read_text())
            if isinstance(data.get('branch'), str) and re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64}|unknown)', data.get('revision', '')):
                return {'branch': data['branch'], 'revision': data['revision']}
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    return source_revision(Path(__file__).resolve().parent.parent)


if __name__ == '__main__':
    import sys
    Path(sys.argv[2]).write_text(json.dumps(source_revision(sys.argv[1])))
