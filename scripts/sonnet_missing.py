"""Print the number of missing Sonnet matrix cells; drop contaminated ones first."""
import glob, json, os, sys
D = ['dangerous_goods','customer_service','patient_intake','know_your_business','aircraft_inspection',
     'warehouse_package_inspection','email_intent','content_flagging','video_annotation','video_classification']
for f in glob.glob('results/sonnet_*.json'):
    try:
        e = sum(1 for r in json.load(open(f))['rows'] if r.get('status') == 'error')
    except Exception:
        e = 99
    if e > 3:
        print('DIRTY', os.path.basename(f), e, file=sys.stderr); os.remove(f)
have = {os.path.basename(f)[:-5] for f in glob.glob('results/sonnet_*.json')}
print(sum(1 for d in D for c in ('acorn', 'baseline') if f'sonnet_{d}_{c}' not in have))
