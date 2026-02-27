from pathlib import Path

from thelocalai.project_context import build_project_context, should_include_project_context


def test_should_include_project_context_detects_structure_questions():
    assert should_include_project_context('where is the voice module file?') is True
    assert should_include_project_context('hello there') is False


def test_build_project_context_lists_relevant_paths(tmp_path: Path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'voice.py').write_text('print("voice")')
    (tmp_path / 'pkg' / 'chat_logic.py').write_text('print("chat")')
    (tmp_path / 'README.md').write_text('hi')

    context = build_project_context('where is voice code', root=tmp_path)

    assert 'PROJECT SNAPSHOT:' in context
    assert 'pkg/voice.py' in context
