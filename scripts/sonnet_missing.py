"""Print the number of missing Sonnet matrix cells; drop contaminated ones first."""
import glob, json, os, sys
D = ['dangerous_goods','customer_service','patient_intake','know_your_business','aircraft_inspection',
     'warehouse_package_inspection','email_intent','content_flagging','video_annotation','video_classification']
for f in [x for x in glob.glob('results/sonnet_*.json') if not x.endswith('.partial.json')]:
    try:
        e = sum(1 for r in json.load(open(f))['rows'] if r.get('status') == 'error')
    except Exception:
        e = 99
    if e > 3:
        # Demote to a checkpoint instead of discarding: keep the good rows,
        # drop the error rows, and let the resume path redo only those.
        d = json.load(open(f))
        good = [r for r in d['rows'] if r.get('status') != 'error']
        open(f + '.partial.json', 'w').write(json.dumps(good))
        print('DIRTY->checkpoint', os.path.basename(f), 'errors', e, 'kept', len(good), file=sys.stderr)
        os.remove(f)
have = {os.path.basename(f)[:-5] for f in glob.glob('results/sonnet_*.json') if not f.endswith('.partial.json')}
print(sum(1 for d in D for c in ('acorn', 'baseline') if f'sonnet_{d}_{c}' not in have))
