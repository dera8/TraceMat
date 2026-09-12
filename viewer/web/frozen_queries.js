/* Makes the Ask panel usable without a local language model.
 *
 * The viewer compiles a question into a typed query with `nlqTranslate`, which
 * calls a model served at localhost. On a hosted page that model is absent, so
 * the panel can only report the failure. Execution, however, already happens in
 * the browser and is deterministic: only compilation needs the model.
 *
 * This file ships the reference compilation for the benchmark's frozen
 * questions and extends `nlqDirectQuery`, the hook the viewer already consults
 * before reaching for the model. Picking one of those questions therefore shows
 * the typed query it compiles to and the rows the graph actually returns, with
 * no model involved. Anything typed by hand still goes to the model, and still
 * says so when it cannot be reached.
 *
 * The panel states that the query is the benchmark's canonical one rather than
 * a live compilation. Presenting a stored answer as a fresh one would be the
 * one thing this demo must not do.
 */
(function (g) {
  const norm = (s) => String(s || '').trim().toLowerCase().replace(/[\s?.!]+$/g, '');
  let frozen = [];

  // La sostituzione va fatta dopo che gli script inline hanno girato: il viewer
  // dichiara `function nlqDirectQuery(...)`, e una dichiarazione di funzione
  // sovrascrive qualunque assegnazione fatta prima che il suo script venga
  // valutato. Wrappare qui, sull'evento load, e' l'unico momento sicuro.
  function installHook() {
    const previous = g.nlqDirectQuery;
    g.nlqDirectQuery = function (question) {
      const hit = frozen.find((f) => norm(f.question) === norm(question));
      if (hit) {
        return {
          think: `Frozen benchmark question ${hit.id}. The query below is the ` +
                 `canonical compilation used in the paper's evaluation, not a ` +
                 `live one; it is executed over the graph in this browser.`,
          query: hit.query,
        };
      }
      return typeof previous === 'function' ? previous(question) : null;
    };
  }

  g.addEventListener('load', async () => {
    const bar = document.getElementById('nlqBar');
    const box = document.getElementById('nlqQ');
    const go = document.getElementById('nlqGo');
    if (!bar || !box || !go) return;

    try {
      const r = await fetch('assets/frozen_queries.json');
      if (!r.ok) return;
      frozen = (await r.json()).questions || [];
    } catch (e) {
      return;                       // nessun file: il pannello resta com'era
    }
    if (!frozen.length) return;
    installHook();

    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:6px;align-items:center;justify-content:center;' +
                        'font-size:10px;margin-top:4px;flex-wrap:wrap';

    const label = document.createElement('span');
    label.textContent = 'no model needed:';
    label.style.color = '#667';

    const pick = document.createElement('select');
    pick.style.cssText = 'font-size:10px;padding:2px 4px;border-radius:8px;' +
                         'border:1px solid #789;background:#fff;max-width:430px';
    pick.appendChild(new Option('frozen benchmark questions…', ''));
    frozen.forEach((f) => {
      const short = f.question.length > 78 ? f.question.slice(0, 75) + '…' : f.question;
      const flag = f.query.op === 'unsupported' ? ' [unanswerable]' : '';
      pick.appendChild(new Option(`${f.id} · ${short}${flag}`, f.id));
    });
    pick.onchange = () => {
      const f = frozen.find((x) => x.id === pick.value);
      if (!f) return;
      box.value = f.question;
      go.click();                   // nlqDirectQuery intercetta: nessun modello
    };

    row.appendChild(label);
    row.appendChild(pick);
    bar.parentNode.insertBefore(row, bar.nextSibling);
  });
})(window);
