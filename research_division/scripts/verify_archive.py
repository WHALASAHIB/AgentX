import json
a = json.load(open('C:/Trading/research_division/state/research_hypotheses.json'))
print(f'Archive now has {a["metadata"]["total_ideas"]} ideas.')
print(f'Families: {a["metadata"]["families_covered"]}')
coverage_str = {k: len(v) for k, v in a['coverage_map'].items()}
print(f'Coverage: {coverage_str}')
