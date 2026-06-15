/* chat-highlight.js — tiny, offline, XSS-safe syntax highlighter for the
 * Chat tab's rendered code blocks (chat.html owns the Markdown rendering;
 * this only colours the code inside a fenced block).
 *
 * Why hand-rolled instead of vendoring highlight.js:
 *   - The lab defaults to LAB_MODE=airgapped — no CDN fetch allowed.
 *   - It colours untrusted model output on other people's machines, so it
 *     must be XSS-safe. It is safe by construction: every token is HTML-
 *     escaped before any <span> is emitted; no raw input is passed through.
 *   - The repo is sensitive to git bloat; a few KB beats a vendored blob.
 *
 * Public API: window.highlightCode(codeString, langString) -> safe HTML.
 * The returned HTML's textContent equals the original code, so a "copy"
 * button reading code.textContent still yields clean, unhighlighted source.
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  var KEYWORDS = {
    python: ['def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while',
      'import', 'from', 'as', 'with', 'try', 'except', 'finally', 'raise',
      'in', 'not', 'and', 'or', 'is', 'lambda', 'yield', 'global', 'nonlocal',
      'pass', 'break', 'continue', 'assert', 'del', 'async', 'await',
      'True', 'False', 'None', 'self'],
    javascript: ['function', 'return', 'if', 'else', 'for', 'while', 'const',
      'let', 'var', 'class', 'extends', 'new', 'this', 'import', 'export',
      'from', 'default', 'try', 'catch', 'finally', 'throw', 'typeof',
      'instanceof', 'in', 'of', 'await', 'async', 'yield', 'switch', 'case',
      'break', 'continue', 'do', 'delete', 'void', 'null', 'undefined',
      'true', 'false'],
    bash: ['if', 'then', 'else', 'elif', 'fi', 'for', 'in', 'do', 'done',
      'while', 'case', 'esac', 'function', 'return', 'export', 'local',
      'echo', 'cd', 'source', 'set', 'unset', 'read'],
    go: ['func', 'package', 'import', 'var', 'const', 'type', 'struct',
      'interface', 'return', 'if', 'else', 'for', 'range', 'go', 'defer',
      'chan', 'map', 'select', 'switch', 'case', 'default', 'break',
      'continue', 'nil', 'true', 'false'],
    rust: ['fn', 'let', 'mut', 'const', 'struct', 'enum', 'impl', 'trait',
      'pub', 'use', 'mod', 'match', 'if', 'else', 'for', 'while', 'loop',
      'return', 'self', 'Self', 'async', 'await', 'move', 'ref', 'where',
      'true', 'false', 'None', 'Some', 'Ok', 'Err'],
    sql: ['select', 'from', 'where', 'insert', 'into', 'values', 'update',
      'set', 'delete', 'create', 'table', 'drop', 'alter', 'join', 'left',
      'right', 'inner', 'outer', 'on', 'group', 'by', 'order', 'having',
      'limit', 'as', 'and', 'or', 'not', 'null', 'distinct'],
    c: ['int', 'char', 'float', 'double', 'void', 'return', 'if', 'else',
      'for', 'while', 'struct', 'typedef', 'const', 'static', 'sizeof',
      'switch', 'case', 'break', 'continue', 'include', 'define', 'class',
      'public', 'private', 'new', 'delete', 'nullptr', 'true', 'false'],
    json: []
  };
  KEYWORDS.py = KEYWORDS.python;
  KEYWORDS.js = KEYWORDS.javascript;
  KEYWORDS.ts = KEYWORDS.typescript = KEYWORDS.javascript;
  KEYWORDS.sh = KEYWORDS.shell = KEYWORDS.zsh = KEYWORDS.bash;
  KEYWORDS.cpp = KEYWORDS['c++'] = KEYWORDS.c;

  function commentStyle(lang) {
    if (['python', 'py', 'bash', 'sh', 'shell', 'zsh', 'ruby', 'yaml', 'yml', 'toml'].indexOf(lang) >= 0) return 'hash';
    if (lang === 'sql') return 'dashdash';
    return 'slash';
  }

  function highlightCode(code, lang) {
    code = String(code == null ? '' : code);
    lang = (lang || '').toLowerCase();
    var kwSet = Object.create(null);
    (KEYWORDS[lang] || []).forEach(function (k) { kwSet[k] = true; });
    var style = commentStyle(lang);

    var parts = [];
    if (style === 'hash') parts.push('(#[^\\n]*)');
    else if (style === 'dashdash') parts.push('(--[^\\n]*)');
    else parts.push('(//[^\\n]*|/\\*[\\s\\S]*?\\*/)');
    parts.push('("""[\\s\\S]*?"""|\'\'\'[\\s\\S]*?\'\'\'|"(?:\\\\.|[^"\\\\])*"|\'(?:\\\\.|[^\'\\\\])*\'|`(?:\\\\.|[^`\\\\])*`)');
    parts.push('(\\b\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b)');
    parts.push('([A-Za-z_$][\\w$]*)');
    var re = new RegExp(parts.join('|'), 'g');

    var out = '';
    var last = 0;
    var m;
    while ((m = re.exec(code)) !== null) {
      out += esc(code.slice(last, m.index));
      last = re.lastIndex;
      if (m[1] != null) {
        out += '<span class="hl-com">' + esc(m[1]) + '</span>';
      } else if (m[2] != null) {
        out += '<span class="hl-str">' + esc(m[2]) + '</span>';
      } else if (m[3] != null) {
        out += '<span class="hl-num">' + esc(m[3]) + '</span>';
      } else if (m[4] != null) {
        var id = m[4];
        if (kwSet[id]) {
          out += '<span class="hl-kw">' + esc(id) + '</span>';
        } else if (/^\s*\(/.test(code.slice(re.lastIndex))) {
          out += '<span class="hl-fn">' + esc(id) + '</span>';
        } else {
          out += esc(id);
        }
      }
    }
    out += esc(code.slice(last));
    return out;
  }

  if (typeof window !== 'undefined') window.highlightCode = highlightCode;
  if (typeof module !== 'undefined' && module.exports) module.exports = { highlightCode: highlightCode };
})();
