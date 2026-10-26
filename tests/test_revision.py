from app.revision import source_revision

SHA = 'a' * 40


def test_loose_and_packed_branches(tmp_path):
    git = tmp_path / '.git'
    (git / 'refs/heads/feature').mkdir(parents=True)
    (git / 'HEAD').write_text('ref: refs/heads/feature/footer\n')
    ref = git / 'refs/heads/feature/footer'
    ref.write_text(SHA + '\n')
    assert source_revision(tmp_path) == {'branch': 'feature/footer', 'revision': SHA}
    ref.unlink()
    (git / 'packed-refs').write_text('# pack-refs\n' + SHA + ' refs/heads/feature/footer\n')
    assert source_revision(tmp_path)['revision'] == SHA


def test_detached_and_missing_metadata(tmp_path):
    assert source_revision(tmp_path) == {'branch': 'unknown', 'revision': 'unknown'}
    # Same layout as the metadata-only Docker build stage.
    (tmp_path / 'HEAD').write_text(SHA)
    assert source_revision(tmp_path) == {'branch': 'detached', 'revision': SHA}
    (tmp_path / 'HEAD').write_text('invalid')
    assert source_revision(tmp_path)['revision'] == 'unknown'


def test_footer_uses_running_revision(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setattr('app.main.build_revision', lambda: {'branch': 'feature/<footer>', 'revision': SHA})
    with TestClient(create_app(str(tmp_path / 'db.sqlite3'))) as client:
        html = client.get('/').text
        assert 'feature/&lt;footer&gt;' in html
        assert '/tree/feature%2F%3Cfooter%3E' in html
        assert '/commit/' + SHA in html
        assert '__SOURCE_' not in html and '__REVISION_' not in html
        assert client.get('/api/health').json()['source']['revision'] == SHA
