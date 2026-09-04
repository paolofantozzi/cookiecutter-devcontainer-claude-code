from pathlib import Path

import jinja2

from cdforge.renderer import render_tree


def test_render_tree_substitutes_filenames_and_content(tmp_path: Path) -> None:
    source_root = tmp_path / 'source'
    (source_root / '{{package_name}}').mkdir(parents=True)
    (source_root / '{{package_name}}' / 'module.py.j2').write_text(
        'value = "{{ greeting }}"\n', encoding='utf-8'
    )
    output_dir = tmp_path / 'output'

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(source_root)), keep_trailing_newline=True
    )
    written = render_tree(env, source_root, output_dir, {'package_name': 'demo', 'greeting': 'hi'})

    rendered_file = output_dir / 'demo' / 'module.py'
    assert rendered_file in written
    assert rendered_file.read_text(encoding='utf-8') == 'value = "hi"\n'


def test_render_tree_skips_files_that_render_to_blank(tmp_path: Path) -> None:
    source_root = tmp_path / 'source'
    source_root.mkdir()
    (source_root / 'optional.txt.j2').write_text(
        '{% if include_it %}content{% endif %}\n', encoding='utf-8'
    )
    output_dir = tmp_path / 'output'

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(source_root)))
    written = render_tree(env, source_root, output_dir, {'include_it': False})

    assert written == []
    assert not (output_dir / 'optional.txt').exists()


def test_render_tree_copies_non_template_files_verbatim(tmp_path: Path) -> None:
    source_root = tmp_path / 'source'
    source_root.mkdir()
    (source_root / 'static.txt').write_text('{{ not_a_variable }}', encoding='utf-8')
    output_dir = tmp_path / 'output'

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(source_root)))
    render_tree(env, source_root, output_dir, {})

    assert (output_dir / 'static.txt').read_text(encoding='utf-8') == '{{ not_a_variable }}'
