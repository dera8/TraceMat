(function (g) {
  // Adds three quick-access shortcut buttons under the NL-query bar. The
  // actual radio-materials/LiDAR-pseudoreflectance/state-change query
  // execution now lives natively in the viewer's own nlqExecute/SCHEMA_PROMPT
  // (kept in sync with queries.py) - this file no longer monkey-patches
  // nlqExecute/nlqTranslate with a second, divergent implementation, since
  // that produced answers that were inconsistent with the real graph-query
  // logic (e.g. a stricter/looser eligibility test) and silently shadowed
  // native support once it was added.
  g.addEventListener('load', () => {
    const q = document.getElementById('nlqQ'), go = document.getElementById('nlqGo'), bar = document.getElementById('nlqBar');
    if (!q || !go || !bar) return;
    const modes = document.createElement('div');
    modes.style.cssText = 'display:flex;gap:5px;justify-content:center;font-size:10px';
    [
      ['Radio materials', 'Show surfaces with radio materials available at 3.5 GHz.'],
      ['LiDAR pseudo-reflectance', 'Show road surfaces coloured by LiDAR pseudo-reflectance.'],
      ['PBR / reset', null],
    ].forEach(([label, text]) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.style.cssText = 'font-size:10px;padding:3px 8px;border-radius:10px;border:1px solid #789;background:#fff;cursor:pointer';
      b.onclick = () => {
        if (text) { q.value = text; go.click(); }
        else { const r = document.getElementById('nlqReset'); if (r) r.click(); }
      };
      modes.appendChild(b);
    });
    bar.parentNode.insertBefore(modes, bar.nextSibling);
  });
})(window);
