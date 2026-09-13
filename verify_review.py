"""Verify the anonymous review snapshot without modifying its data."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'audit'))
from graph_validation import validate_graph
from score_audit import summary

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild', action='store_true', help='Also rebuild each graph in memory and compare it to the anonymous snapshot.')
    args = parser.parse_args()
    if args.rebuild:
        from build_scene_graphs import build_scene
    total = grounded = 0
    for scene in ('Maradona', 'Siemensstadt', 'CanaryWharf'):
        graph = read_json(ROOT / 'data' / 'graphs' / (scene + '_graph.json'))
        validate_graph(graph)
        meta = graph['graph']
        for name, expected in zip(meta['source_files'], meta['source_file_sha256']):
            actual = hashlib.sha256((ROOT / name.replace('\\', '/')).read_bytes()).hexdigest()
            assert actual == expected, 'Input fingerprint mismatch: ' + name
        for node in graph['nodes']:
            if node.get('grounding_status') in ('grounded', 'unresolved'):
                total += 1
                grounded += node['grounding_status'] == 'grounded'
        if args.rebuild:
            rebuilt = build_scene(scene, timestamp=meta['generation_timestamp'])
            assert rebuilt == graph, 'Rebuilt graph differs: ' + scene
        print('PASS graph, inputs' + (', rebuild: ' if args.rebuild else ': ') + scene)
    assert (grounded, total) == (3717, 3918)
    print(f'PASS grounding coverage: {grounded}/{total} = {100 * grounded / total:.1f}%')
    with (ROOT / 'audit' / 'grounding_audit_labelled.csv').open(encoding='utf-8-sig', newline='') as f:
        metrics = summary(list(csv.DictReader(f)))
    recorded = next(r for r in read_json(ROOT / 'results' / 'grounding_audit_metrics.json')['rows'] if r['group'] == 'overall')
    for key, value in metrics.items():
        assert recorded[key] == value, 'Audit mismatch: ' + key
    print('PASS audit: 126/133 settled cases; 17 uncertain; 94.7% precision')
    manifest = ROOT / 'MANIFEST.sha256.json'
    if manifest.exists():
        for name, expected in read_json(manifest).items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, 'Package file changed: ' + name
        print('PASS package file fingerprints')
    print('All requested checks passed.')

if __name__ == '__main__':
    main()
