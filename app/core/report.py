"""Human-readable restructure reports.

The CSV from `migration.write_report` is a faithful log, but a non-technical
user can't read it. This module turns the same results into:

  - an interactive HTML page (opens in any browser, fully offline, no
    external files): summary, a collapsible "after" tree showing what each
    file used to be called, a "before" tree showing where each file went,
    a searchable list of every change, and any problems in plain words;
  - a print layout of the same content, which the UI renders to PDF
    (see app/ui/report_export.py — Qt is kept out of core).

Pure functions over `MigrationResult`s; nothing here touches the moved files.
"""
from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.migration import MigrationResult

# What happened to one file, from the user's point of view.
RENAMED = "renamed"        # same folder, new name
MOVED = "moved"            # new folder, same name
MOVED_RENAMED = "moved_renamed"
FAILED = "failed"          # left where it was

KIND_LABELS = {
    RENAMED: "Renamed",
    MOVED: "Moved",
    MOVED_RENAMED: "Moved & renamed",
    FAILED: "Not changed (problem)",
}


@dataclass
class FileChange:
    old_rel: str
    new_rel: str
    kind: str
    error: str | None = None

    @property
    def old_name(self) -> str:
        return Path(self.old_rel).name

    @property
    def new_name(self) -> str:
        return Path(self.new_rel).name

    @property
    def old_folder(self) -> str:
        return _folder_label(self.old_rel)

    @property
    def new_folder(self) -> str:
        return _folder_label(self.new_rel)


def _folder_label(rel: str) -> str:
    parent = Path(rel).parent.as_posix()
    return "(top folder)" if parent == "." else parent


@dataclass
class ReportData:
    root: str
    created_at: float
    changes: list[FileChange]
    new_folders: list[str] = field(default_factory=list)       # relative to root
    emptied_folders: list[str] = field(default_factory=list)   # relative to root

    def count(self, *kinds: str) -> int:
        return sum(1 for c in self.changes if c.kind in kinds)


def _rel(root: Path, p: str) -> str:
    try:
        return Path(p).relative_to(root).as_posix()
    except ValueError:
        return Path(p).as_posix()


def build_report(
    root: str, results: list[MigrationResult], new_folders: set[str] | None = None
) -> ReportData:
    root_path = Path(root)
    changes: list[FileChange] = []
    for r in results:
        old_rel, new_rel = _rel(root_path, r.old_path), _rel(root_path, r.new_path)
        if r.status != "success":
            kind = FAILED
        elif Path(old_rel).parent == Path(new_rel).parent:
            kind = RENAMED
        elif Path(old_rel).name == Path(new_rel).name:
            kind = MOVED
        else:
            kind = MOVED_RENAMED
        changes.append(FileChange(old_rel, new_rel, kind, r.error))

    # Folders files were moved *out of* that are now empty (or gone) — the
    # user will likely want to delete these, so they're listed explicitly.
    emptied: set[str] = set()
    for c in changes:
        if c.kind in (MOVED, MOVED_RENAMED):
            parent = Path(c.old_rel).parent
            if parent == Path("."):
                continue
            folder = root_path / parent
            try:
                is_empty = not folder.exists() or not any(
                    p for p in folder.iterdir() if p.name != ".DS_Store"
                )
            except OSError:
                is_empty = False
            if is_empty:
                emptied.add(parent.as_posix())

    return ReportData(
        root=root,
        created_at=time.time(),
        changes=changes,
        new_folders=sorted(_rel(root_path, f) for f in (new_folders or set())),
        emptied_folders=sorted(emptied),
    )


# -- trees ------------------------------------------------------------------------
@dataclass
class _Node:
    name: str
    path: str  # relative to root
    folders: dict[str, "_Node"] = field(default_factory=dict)
    files: list[tuple[str, FileChange]] = field(default_factory=list)

    def file_count(self) -> int:
        return len(self.files) + sum(f.file_count() for f in self.folders.values())


def _tree(changes: list[FileChange], side: str) -> _Node:
    """side="after": files at their new location (failed ones stay put);
    side="before": files at their original location."""
    root = _Node("", "")
    for c in changes:
        rel = c.old_rel if side == "before" or c.kind == FAILED else c.new_rel
        parts = rel.split("/")
        node = root
        for i, part in enumerate(parts[:-1]):
            node = node.folders.setdefault(part, _Node(part, "/".join(parts[: i + 1])))
        node.files.append((parts[-1], c))
    return root


def _is_new_branch(path: str, new_folders: set[str]) -> bool:
    """Badge only the top-most new folder of a new branch — everything
    under it is new too, and repeating the badge on every level is noise."""
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    return path in new_folders and parent not in new_folders


def _sorted_folders(node: _Node) -> list[_Node]:
    return sorted(node.folders.values(), key=lambda n: n.name.lower())


def _sorted_files(node: _Node) -> list[tuple[str, FileChange]]:
    return sorted(node.files, key=lambda f: f[0].lower())


# -- interactive HTML -------------------------------------------------------------------
def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _file_note(c: FileChange, side: str) -> str:
    if c.kind == FAILED:
        return f'<span class="note bad">stayed here — {_e(c.error or "could not be moved")}</span>'
    if side == "after":
        if c.kind == RENAMED:
            return f'<span class="note">was <b>{_e(c.old_name)}</b></span>'
        return f'<span class="note">came from <b>{_e(c.old_rel)}</b></span>'
    # before
    if c.kind == RENAMED:
        return f'<span class="note">renamed to <b>{_e(c.new_name)}</b></span>'
    return f'<span class="note">moved to <b>{_e(c.new_rel)}</b></span>'


def _html_tree(node: _Node, side: str, new_folders: set[str], emptied: set[str]) -> str:
    out = []
    for folder in _sorted_folders(node):
        badge = ""
        if side == "after" and _is_new_branch(folder.path, new_folders):
            badge = '<span class="badge new">new folder</span>'
        if side == "before" and folder.path in emptied:
            badge = '<span class="badge empty">now empty</span>'
        n = folder.file_count()
        out.append(
            f'<details open><summary><span class="folder">📁 {_e(folder.name)}</span>'
            f'<span class="count">{n} file{"s" if n != 1 else ""}</span>{badge}</summary>'
            f'<div class="children">{_html_tree(folder, side, new_folders, emptied)}</div></details>'
        )
    for name, c in _sorted_files(node):
        search = _e(f"{c.old_rel} {c.new_rel}".lower())
        out.append(
            f'<div class="file k-{c.kind}" data-search="{search}">'
            f'<span class="dot"></span><span class="fname">{_e(name)}</span>{_file_note(c, side)}</div>'
        )
    return "".join(out)


_HTML_CSS = """
:root { --bg:#f7f8fa; --surface:#fff; --border:#d8dce1; --text:#1f2430; --muted:#6b7280;
  --accent:#2563eb; --green:#15803d; --amber:#b45309; --red:#b91c1c; --purple:#7c3aed; }
@media (prefers-color-scheme: dark) { :root { --bg:#14161b; --surface:#1d2027; --border:#333844;
  --text:#e6e8ec; --muted:#9aa1ad; --accent:#6b9bff; --green:#4ade80; --amber:#fbbf24; --red:#f87171; --purple:#b49cff; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 28px 16px 60px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 20px; word-break: break-all; }
.cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap:10px; margin-bottom: 20px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px 14px; }
.card .n { font-size: 24px; font-weight: 700; }
.card .l { color: var(--muted); font-size: 12px; }
.card.bad .n { color: var(--red); }
.tabs { display:flex; gap:4px; flex-wrap: wrap; border-bottom:1px solid var(--border); margin-bottom: 12px; }
.tab { background:none; border:none; padding:8px 14px; cursor:pointer; color:var(--muted); font:inherit; border-bottom:2px solid transparent; }
.tab.on { color:var(--text); font-weight:600; border-bottom-color: var(--accent); }
.panel { display:none; background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; }
.panel.on { display:block; }
.toolbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom: 10px; }
.toolbar input { flex:1; min-width: 180px; padding:7px 10px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); font:inherit; }
.toolbar button { padding:6px 12px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--text); cursor:pointer; font:inherit; }
.explain { color: var(--muted); margin: 0 0 10px; }
details { margin-left: 0; }
.children { margin-left: 18px; border-left: 1px dashed var(--border); padding-left: 10px; }
summary { cursor:pointer; padding:3px 0; list-style-position: outside; }
.folder { font-weight: 600; }
.count { color: var(--muted); font-size: 12px; margin-left: 8px; }
.badge { font-size: 11px; border-radius: 999px; padding: 1px 8px; margin-left: 8px; }
.badge.new { background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent); }
.badge.empty { background: color-mix(in srgb, var(--amber) 15%, transparent); color: var(--amber); }
.file { padding: 3px 0 3px 4px; display:flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; flex: none; }
.k-renamed .dot { background: var(--green); } .k-moved .dot { background: var(--accent); }
.k-moved_renamed .dot { background: var(--purple); } .k-failed .dot { background: var(--red); }
.fname { word-break: break-all; }
.note { color: var(--muted); font-size: 12px; word-break: break-all; }
.note.bad { color: var(--red); }
.legend { display:flex; gap:14px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin-bottom: 10px; }
.legend span { display:inline-flex; align-items:center; gap:6px; }
table { width:100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align:left; padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; word-break: break-all; }
th { color: var(--muted); font-weight: 600; }
.hidden { display:none !important; }
.ok { color: var(--green); }
ul.plain { margin: 0; padding-left: 18px; }
@media print { .tabs, .toolbar { display:none; } .panel { display:block !important; border:none; padding:0; margin-bottom:24px; } }
"""

_HTML_JS = """
const tabs = document.querySelectorAll('.tab');
tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x => x.classList.toggle('on', x === t));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('on', p.id === t.dataset.panel));
}));
function setOpen(panel, open) { panel.querySelectorAll('details').forEach(d => d.open = open); }
document.querySelectorAll('[data-expand]').forEach(b => b.addEventListener('click', () =>
  setOpen(document.getElementById(b.dataset.expand), b.dataset.open === '1')));
document.querySelectorAll('input[data-filter]').forEach(inp => inp.addEventListener('input', () => {
  const q = inp.value.trim().toLowerCase();
  const panel = document.getElementById(inp.dataset.filter);
  panel.querySelectorAll('[data-search]').forEach(el => el.classList.toggle('hidden', q && !el.dataset.search.includes(q)));
  // Hide folders with nothing visible inside; open the ones that match.
  [...panel.querySelectorAll('details')].reverse().forEach(d => {
    const any = d.querySelector('.file:not(.hidden)');
    d.classList.toggle('hidden', !!q && !any);
    if (q && any) d.open = true;
  });
}));
"""


def _legend() -> str:
    return (
        '<div class="legend">'
        '<span class="k-renamed"><span class="dot"></span>Renamed</span>'
        '<span class="k-moved"><span class="dot"></span>Moved</span>'
        '<span class="k-moved_renamed"><span class="dot"></span>Moved &amp; renamed</span>'
        '<span class="k-failed"><span class="dot"></span>Problem — left as it was</span>'
        "</div>"
    )


def _when(data: ReportData) -> str:
    return time.strftime("%d %b %Y, %I:%M %p", time.localtime(data.created_at))


def render_interactive_html(data: ReportData) -> str:
    new_folders, emptied = set(data.new_folders), set(data.emptied_folders)
    after = _html_tree(_tree(data.changes, "after"), "after", new_folders, emptied)
    before = _html_tree(_tree(data.changes, "before"), "before", new_folders, emptied)
    failed = [c for c in data.changes if c.kind == FAILED]
    done = len(data.changes) - len(failed)

    rows = "".join(
        f'<tr data-search="{_e((c.old_rel + " " + c.new_rel).lower())}">'
        f"<td>{_e(c.old_name)}<div class='note'>{_e(c.old_folder)}</div></td>"
        f"<td>{_e(c.new_name)}<div class='note'>{_e(c.new_folder)}</div></td>"
        f"<td class='k-{c.kind}'><span class='dot'></span> {KIND_LABELS[c.kind]}</td></tr>"
        for c in sorted(data.changes, key=lambda c: c.old_rel.lower())
    )
    problems = (
        "<p class='ok'>✓ Every file was moved/renamed successfully.</p>"
        if not failed else
        "<p class='explain'>These files were <b>not</b> changed and are still where they were. "
        "Nothing was lost.</p><table><tr><th>File</th><th>Why</th></tr>"
        + "".join(f"<tr><td>{_e(c.old_rel)}</td><td>{_e(c.error or '')}</td></tr>" for c in failed)
        + "</table>"
    )
    emptied_html = (
        "<h3>Folders that are now empty</h3><p class='explain'>Everything in these folders was moved "
        "into the new structure. You can delete them if you no longer need them.</p><ul class='plain'>"
        + "".join(f"<li>{_e(f)}</li>" for f in data.emptied_folders) + "</ul>"
        if data.emptied_folders else ""
    )

    def card(n: int, label: str, cls: str = "") -> str:
        return f'<div class="card {cls}"><div class="n">{n}</div><div class="l">{label}</div></div>'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Restructure Report</title><style>{_HTML_CSS}</style></head>
<body><main>
<h1>Restructure report</h1>
<p class="sub">{_e(data.root)} · {_when(data)}</p>
<div class="cards">
  {card(done, "files reorganized")}
  {card(data.count(RENAMED), "renamed in place")}
  {card(data.count(MOVED, MOVED_RENAMED), "moved to a new folder")}
  {card(len(data.new_folders), "new folders created")}
  {card(len(failed), "problems", "bad" if failed else "")}
</div>
<div class="tabs">
  <button class="tab on" data-panel="p-after">New structure</button>
  <button class="tab" data-panel="p-before">Where files came from</button>
  <button class="tab" data-panel="p-list">All changes</button>
  <button class="tab" data-panel="p-problems">Problems{f" ({len(failed)})" if failed else ""}</button>
</div>
<section class="panel on" id="p-after">
  <p class="explain">Your folder as it looks now. Under each file you can see what it used to be called or where it came from.</p>
  <div class="toolbar"><input data-filter="p-after" placeholder="Find a file (old or new name)…">
    <button data-expand="p-after" data-open="1">Expand all</button><button data-expand="p-after" data-open="0">Collapse all</button></div>
  {_legend()}{after}
</section>
<section class="panel" id="p-before">
  <p class="explain">Your folder as it was before, and where each file went.</p>
  <div class="toolbar"><input data-filter="p-before" placeholder="Find a file (old or new name)…">
    <button data-expand="p-before" data-open="1">Expand all</button><button data-expand="p-before" data-open="0">Collapse all</button></div>
  {_legend()}{before}{emptied_html}
</section>
<section class="panel" id="p-list">
  <div class="toolbar"><input data-filter="p-list" placeholder="Find a file (old or new name)…"></div>
  <table><tr><th>Before</th><th>After</th><th>What happened</th></tr>{rows}</table>
</section>
<section class="panel" id="p-problems">{problems}</section>
</main><script>{_HTML_JS}</script>
</body></html>"""


# -- print layout (for PDF) ---------------------------------------------------------------
# Kept to the HTML subset Qt's QTextDocument renders: tables, colored spans,
# margins — no flexbox, no JS, no emoji (PDF fonts may lack them).
_KIND_COLORS = {RENAMED: "#15803d", MOVED: "#2563eb", MOVED_RENAMED: "#7c3aed", FAILED: "#b91c1c"}
_INDENT_PX = 18


def _print_tree(node: _Node, side: str, new_folders: set[str], emptied: set[str], depth: int = 0) -> str:
    out = []
    pad = depth * _INDENT_PX
    for folder in _sorted_folders(node):
        badge = ""
        if side == "after" and _is_new_branch(folder.path, new_folders):
            badge = ' <span style="color:#2563eb; font-size:8pt;">[NEW FOLDER]</span>'
        if side == "before" and folder.path in emptied:
            badge = ' <span style="color:#b45309; font-size:8pt;">[NOW EMPTY]</span>'
        n = folder.file_count()
        out.append(
            f'<p style="margin:2px 0 0 {pad}px;"><b>&#9662; {_e(folder.name)}/</b>'
            f' <span style="color:#6b7280; font-size:8pt;">({n} file{"s" if n != 1 else ""})</span>{badge}</p>'
        )
        out.append(_print_tree(folder, side, new_folders, emptied, depth + 1))
    for name, c in _sorted_files(node):
        color = _KIND_COLORS[c.kind]
        if c.kind == FAILED:
            note = f"not changed: {c.error or 'problem'}"
        elif side == "after":
            note = f"was {c.old_name}" if c.kind == RENAMED else f"from {c.old_rel}"
        else:
            note = f"renamed to {c.new_name}" if c.kind == RENAMED else f"moved to {c.new_rel}"
        out.append(
            f'<p style="margin:1px 0 0 {pad}px;"><span style="color:{color};">&#9679;</span> {_e(name)}'
            f'<br><span style="color:#6b7280; font-size:8pt;">&nbsp;&nbsp;&nbsp;&nbsp;{_e(note)}</span></p>'
        )
    return "".join(out)


def render_print_html(data: ReportData) -> str:
    new_folders, emptied = set(data.new_folders), set(data.emptied_folders)
    failed = [c for c in data.changes if c.kind == FAILED]
    done = len(data.changes) - len(failed)
    legend = " &nbsp; ".join(
        f'<span style="color:{_KIND_COLORS[k]};">&#9679;</span> {KIND_LABELS[k]}' for k in (RENAMED, MOVED, MOVED_RENAMED, FAILED)
    )

    def stat(n: int, label: str, color: str = "#1f2430") -> str:
        return (f'<td style="padding:6px 14px 6px 0;"><span style="font-size:16pt; font-weight:bold; color:{color};">{n}</span>'
                f'<br><span style="color:#6b7280; font-size:8pt;">{label}</span></td>')

    problems = (
        '<p style="color:#15803d;">Every file was moved/renamed successfully.</p>'
        if not failed else
        "<p>These files were <b>not</b> changed and are still where they were. Nothing was lost.</p>"
        '<table width="100%" cellspacing="0" cellpadding="4" border="0">'
        + "".join(f'<tr><td style="border-bottom:1px solid #d8dce1;">{_e(c.old_rel)}</td>'
                  f'<td style="border-bottom:1px solid #d8dce1; color:#b91c1c;">{_e(c.error or "")}</td></tr>' for c in failed)
        + "</table>"
    )
    emptied_html = (
        "<h3>Folders that are now empty</h3><p>Everything in these folders was moved into the new "
        "structure. You can delete them if you no longer need them.</p><ul>"
        + "".join(f"<li>{_e(f)}</li>" for f in data.emptied_folders) + "</ul>"
        if data.emptied_folders else ""
    )
    rows = "".join(
        f'<tr><td style="border-bottom:1px solid #d8dce1;">{_e(c.old_rel)}</td>'
        f'<td style="border-bottom:1px solid #d8dce1;">{_e(c.new_rel)}</td>'
        f'<td style="border-bottom:1px solid #d8dce1; color:{_KIND_COLORS[c.kind]};">{KIND_LABELS[c.kind]}</td></tr>'
        for c in sorted(data.changes, key=lambda c: c.old_rel.lower())
    )

    return f"""<html><body style="font-family:'Helvetica Neue', Helvetica, Arial; font-size:9.5pt; color:#1f2430;">
<h1 style="font-size:18pt; margin-bottom:0;">Restructure report</h1>
<p style="color:#6b7280; margin-top:2px;">{_e(data.root)}<br>{_when(data)}</p>
<table cellspacing="0" cellpadding="0"><tr>
{stat(done, "files reorganized")}{stat(data.count(RENAMED), "renamed in place")}
{stat(data.count(MOVED, MOVED_RENAMED), "moved to a new folder")}{stat(len(data.new_folders), "new folders")}
{stat(len(failed), "problems", "#b91c1c" if failed else "#1f2430")}
</tr></table>
<h2 style="font-size:13pt;">1. New folder structure</h2>
<p style="color:#6b7280;">Your folder as it looks now. Under each file: what it used to be called, or where it came from.</p>
<p style="font-size:8pt;">{legend}</p>
{_print_tree(_tree(data.changes, "after"), "after", new_folders, emptied)}
<h2 style="font-size:13pt; page-break-before:always;">2. Where files came from</h2>
<p style="color:#6b7280;">Your folder as it was before, and where each file went.</p>
{_print_tree(_tree(data.changes, "before"), "before", new_folders, emptied)}
{emptied_html}
<h2 style="font-size:13pt; page-break-before:always;">3. Problems</h2>
{problems}
<h2 style="font-size:13pt;">4. Every change</h2>
<table width="100%" cellspacing="0" cellpadding="4" style="font-size:8pt;">
<tr><th align="left">Before</th><th align="left">After</th><th align="left">What happened</th></tr>{rows}</table>
</body></html>"""
