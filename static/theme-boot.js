/* Apply saved theme before the stylesheet paints. CSP-compatible external script. */
(function () {
  'use strict';
  var theme = 'emerald';
  try {
    var saved = window.localStorage.getItem('tru-atlas-theme');
    if (saved === 'light' || saved === 'blue' || saved === 'emerald') theme = saved;
    else if (saved === 'dark') theme = 'blue'; // Preserve prior v1.1 dark selection.
  } catch (_) { /* Private browsing / storage unavailable: use emerald. */ }
  document.documentElement.dataset.theme = theme;
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'light' ? '#f3f9f7' : theme === 'blue' ? '#090f1b' : '#041319';
}());
