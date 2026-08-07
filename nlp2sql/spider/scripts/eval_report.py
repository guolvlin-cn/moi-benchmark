"""mix50 逐题对比报告"""
import json, sqlite3, os, sys, re
sys.path.insert(0, '/home/vagrant/agent-eval-tools/benchmark_data/spider/test_suite')
from exec_eval import eval_exec_match

SPIDER = '/home/vagrant/agent-eval-tools/benchmark_data/spider/spider_data'

with open(f'{SPIDER}/dev_gold_mix50.sql') as f:
    gold_lines = [l.strip() for l in f if l.strip()]
with open(f'{SPIDER}/pred_mix50_moi.sql') as f:
    pred_lines = [l.strip() for l in f if l.strip()]
DEV = json.load(open(f'{SPIDER}/dev.json'))

def norm(s): return ' '.join(s.upper().split()).strip(' ;')
qmap = {}
for item in DEV:
    qmap[(norm(item['query']), item['db_id'])] = item

def classify(sql):
    u = sql.upper()
    if re.search(r'\(\s*SELECT\b', u) or re.search(r'\bEXCEPT\b|\bINTERSECT\b|\bUNION\b', u): return 'hard'
    if re.search(r'\bJOIN\b', u) or 'GROUP BY' in u: return 'medium'
    return 'easy'

passes, fails = [], []

for i in range(50):
    gl = gold_lines[i]
    gold_sql, db_id = gl.split('\t')[0], gl.split('\t')[1] if '\t' in gl else '?'
    pred_sql = pred_lines[i].strip() if i < len(pred_lines) else ''
    item = qmap.get((norm(gold_sql), db_id))
    question = item['question'] if item else '(not found)'
    diff = classify(gold_sql)
    
    db_path = f'{SPIDER}/database/{db_id}/{db_id}.sqlite'
    conn = sqlite3.connect(db_path); conn.text_factory = str; cur = conn.cursor()
    try: cur.execute(gold_sql); g_rows = cur.fetchall(); g_err = None
    except Exception as e: g_rows = []; g_err = str(e)
    try: cur.execute(pred_sql); p_rows = cur.fetchall(); p_err = None
    except Exception as e: p_rows = []; p_err = str(e)
    conn.close()
    
    if pred_sql.upper().startswith('SELECT'):
        try: passed = eval_exec_match(db_path, pred_sql, gold_sql, plug_value=False, keep_distinct=True, progress_bar_for_each_datapoint=False)
        except: passed = 0
    else: passed = 0
    
    if passed: reason = '✓'
    elif p_err: reason = f'MOI SQL报错: {p_err[:60]}'
    elif not pred_sql.upper().startswith('SELECT'): reason = f'MOI无有效SQL: {pred_sql[:50]}'
    elif len(g_rows) != len(p_rows): reason = f'行数不一致: gold={len(g_rows)}, pred={len(p_rows)}'
    else:
        gs = set(str(r) for r in g_rows); ps = set(str(r) for r in p_rows)
        reason = '结果内容不同' if gs != ps else '评测工具误判'
    
    entry = {'id': i+1, 'db': db_id, 'diff': diff, 'question': question, 'gold_sql': gold_sql, 'pred_sql': pred_sql,
             'g_rows': len(g_rows), 'p_rows': len(p_rows), 'passed': bool(passed), 'reason': reason}
    (passes if passed else fails).append(entry)

# 写报告
out = f'{SPIDER}/report_mix50.txt'
lines = [f'{"="*80}', f'  MOI Spider mix50 逐题报告 — exec = {len(passes)}/50 = {len(passes)/50:.3f}', f'{"="*80}', '']

# 按难度汇总
from collections import Counter
dc = Counter(e['diff'] for e in passes + fails)
for d in ['easy','medium','hard']:
    pp = sum(1 for e in passes if e['diff']==d)
    ff = sum(1 for e in fails if e['diff']==d)
    lines.append(f'  {d}: {pp+ff}题, 通过={pp}, 失败={ff}, exec={pp/(pp+ff):.1%}' if pp+ff else f'  {d}: 0题')
lines.append(f'  总计: 50题, 通过={len(passes)}, exec={len(passes)/50:.1%}')
lines.append('')

# 失败分组
rc = Counter(f['reason'] for f in fails)
lines.append(f'失败: {len(fails)} 题')
for reason, cnt in rc.most_common():
    group = [f for f in fails if f['reason'] == reason]
    lines.append(f'\n【{reason}】({cnt}题)')
    for e in group:
        lines.append(f'  #{e["id"]:02d} [{e["db"]:<15}] [{e["diff"]}]')
        lines.append(f'  问题: {e["question"][:80]}')
        lines.append(f'  Gold: {e["gold_sql"]}')
        lines.append(f'  MOI:  {e["pred_sql"]}')
        lines.append(f'  Gold={e["g_rows"]}行, MOI={e["p_rows"]}行')
        lines.append('')

with open(out, 'w') as f: f.write('\n'.join(lines)+'\n')
print(f'报告: {out}')
print(f'通过: {len(passes)}, 失败: {len(fails)}, exec={len(passes)/50:.3f}')
