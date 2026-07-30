#!/usr/bin/env python3
"""Throwaway, observable state-machine prototype for RAGBench -> MOI."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time, re
from pathlib import Path
from typing import Any

DEFAULT_INPUT = "/Users/muuushroom/gitrepos/moi-benchmark/rag/datasets/downloads/public/ragbench/techqa/test-00000-of-00001.parquet"
DEFAULT_RUN = "runs/offline-smoke"
GENERATOR_VERSION = "0.2.0"

def stable_id(text: str, prefix: str = "doc") -> str:
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"

def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024*1024), b""): digest.update(chunk)
    return digest.hexdigest()

def write_json(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def append_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")

def state(run: Path, stage: str, status: str, **extra):
    p=run/"state.json"; old=json.loads(p.read_text()) if p.exists() else {"backend":"unknown","stages":{}}
    old.setdefault("stages", {})[stage] = {"status":status, "at":time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **extra}; write_json(p, old)

def failed(run: Path, stage: str, exc: Exception):
    msg=str(exc)[:200]
    if os.getenv("MOI_API_KEY"): msg=msg.replace(os.getenv("MOI_API_KEY"), "[redacted]")
    state(run, stage, "FAILED", error_type=type(exc).__name__, error=msg.replace("MOI_API_KEY", "[redacted]"))

def result_stage(result, require_job_id=False):
    if str(result.get("status", "")).startswith("BLOCKED"): return "BLOCKED"
    code=result.get("status_code")
    if not isinstance(code,int) or not 200<=code<300: return "FAILED"
    if "job_status" in result:
        return {"completed":"DONE","pending":"PENDING","processing":"PROCESSING","failed":"FAILED"}.get(str(result.get("job_status")).lower(),"FAILED")
    if not require_job_id or result.get("job_id"): return "DONE"
    return "FAILED"

def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text or "")

def pdf_and_check(path: Path, doc_id: str, text: str) -> dict:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from pypdf import PdfReader
    c=canvas.Canvas(str(path), pagesize=letter); width,height=letter
    page=1; y=height-48; max_width=width-80; segments=[]; blank_line_count=0; wrap_whitespace_replacements=0
    def header():
        c.setFont("Helvetica-Bold",8); c.drawString(40,height-24,f"{doc_id} | page {page}")
    def new_page():
        nonlocal page,y
        c.showPage(); page+=1; y=height-48; header(); c.setFont("Helvetica",9)
    header(); c.setFont("Helvetica",9)
    for source_line in text.splitlines() or [""]:
        line=source_line
        if not line:
            blank_line_count+=1
            y-=12
            if y<40: new_page()
            continue
        current=""
        for ch in line:
            candidate=current+ch
            if current and c.stringWidth(candidate,"Helvetica",9)>max_width:
                split_at=max(current.rfind(" "),current.rfind("\t"))
                if split_at>0:
                    segment=current[:split_at]; current=current[split_at+1:]+ch
                    wrap_whitespace_replacements+=1
                else:
                    segment=current; current=ch
                c.drawString(40,y,segment); segments.append(segment); y-=12
                if y<40: new_page(); c.setFont("Helvetica",9)
            else: current=candidate
        c.drawString(40,y,current); segments.append(current); y-=12
        if y<40: new_page(); c.setFont("Helvetica",9)
    c.save()
    reader=PdfReader(str(path)); pages=[p.extract_text() or "" for p in reader.pages]
    actual_segments=[line for p in pages for line in p.splitlines() if not line.startswith(f"{doc_id} | page ") and line]
    body="\n".join(actual_segments)
    source_norm, extracted_norm=normalized(text), normalized(body)
    seg_expected=hashlib.sha256(json.dumps(segments,ensure_ascii=False).encode()).hexdigest(); seg_actual=hashlib.sha256(json.dumps(actual_segments,ensure_ascii=False).encode()).hexdigest()
    result={"pages":len(reader.pages),"text_extractable":bool(extracted_norm),"extracted_chars":len(body),"source_chars":len(text),"blank_line_count":blank_line_count,"wrap_whitespace_replacements":wrap_whitespace_replacements,"rendered_segments_exact_match":actual_segments==segments,"rendered_segments_sha256":seg_expected,"extracted_segments_sha256":seg_actual,"normalized_text_match":source_norm==extracted_norm,"source_normalized_sha256":hashlib.sha256(source_norm.encode()).hexdigest(),"extracted_normalized_sha256":hashlib.sha256(extracted_norm.encode()).hexdigest()}
    if actual_segments != segments: raise RuntimeError(f"PDF rendered segment mismatch for {doc_id}")
    return result

def extract_evidence(row: dict, docs: list[str]):
    keys=row.get("all_relevant_sentence_keys") or []; sent=row.get("documents_sentences") or []
    out=[]; failures=[]
    for key in keys:
        try:
            # keys convention is document-index + sentence key (e.g. 0b)
            di=0
            while di < len(key) and key[di].isdigit(): di+=1
            di=int(key[:di]); local=key[di:]
            pairs=sent[di]
            match=next((x[1] for x in pairs if x and x[0]==local), None)
            if match: out.append({"sentence_key":key,"document_index":di,"text":match})
            else: failures.append({"sentence_key":key,"reason":"not_found"})
        except Exception as e: failures.append({"sentence_key":key,"reason":f"parse_error:{e}"})
    if not keys: failures.append({"reason":"no_all_relevant_sentence_keys"})
    return out, failures

def prepare(args) -> Path:
    import pyarrow.parquet as pq
    run=Path(args.run); run.mkdir(parents=True,exist_ok=True); state(run,"prepare","RUNNING",input=args.input)
    rows=pq.read_table(args.input).to_pylist(); chosen=[]
    for row in rows:
        q=(row.get("question") or "").strip(); docs=[str(x or "") for x in (row.get("documents") or []) if str(x or "").strip()]
        if q and docs: chosen.append((row,q,docs)); break
    if not chosen: raise RuntimeError("No valid question/documents sample found")
    row,q,docs=chosen[0]; corpus=run/"output"/"pdf"; corpus.mkdir(parents=True, exist_ok=True); records=[]
    for i,text in enumerate(docs):
        did=stable_id(text); pdf=corpus/f"{did}.pdf"; check=pdf_and_check(pdf,did,text)
        records.append({"doc_id":did,"document_index":i,"source":"RAGBench documents","sha256":hashlib.sha256(text.encode()).hexdigest(),"pdf":str(pdf.relative_to(run)),"verification":check})
    evidence,failures=extract_evidence(row,docs)
    write_json(run/"corpus_manifest.json",{"source":args.input,"input_sha256":sha256_file(Path(args.input)),"generator_source_sha256":sha256_file(Path(__file__)),"generator_version":GENERATOR_VERSION,"selected_question_id":row.get("id"),"license_status":"UNREVIEWED_THIRD_PARTY","redistribution_allowed":"UNKNOWN","documents":records,"note":"Only documents are written; RAGBench response/labels are not Gold."})
    append_jsonl(run/"questions.jsonl",[{"question_id":row.get("id"),"question":q,"document_ids":[x["doc_id"] for x in records]}])
    append_jsonl(run/"gold_candidates.jsonl",[{"question_id":row.get("id"),"evidence":evidence,"extraction_failures":failures,"status":"UNREVIEWED_CANDIDATES"}])
    state(run,"prepare","DONE",documents=len(records),evidence=len(evidence),evidence_failures=len(failures)); return run

class MoiAdapter:
    def __init__(self): self.base=os.getenv("MOI_API_URL","https://freetier-01.cn-hangzhou.cluster.matrixonecloud.cn").rstrip("/"); self.key=os.getenv("MOI_API_KEY")
    def headers(self, mode="moi"):
        if not self.key: return {}
        return {"Authorization":f"Bearer {self.key}"} if mode=="probe" else {"moi-key":self.key}
    def destination_ok(self, expected_host):
        from urllib.parse import urlparse
        u=urlparse(self.base)
        return u.scheme=="https" and not u.username and not u.password and bool(u.hostname) and expected_host==u.hostname
    def probe(self):
        import requests
        r=requests.get(self.base+"/byoa/api/v1/datasets",headers=self.headers("probe"),timeout=20,allow_redirects=False)
        if 300<=r.status_code<400: return {"status":"BLOCKED_REDIRECT","status_code":r.status_code}
        if self.key and r.status_code == 200:
            try:
                body=r.json(); data=body.get("data",{}); items=data if isinstance(data,list) else data.get("datasets",[])
                return {"status":"AUTHENTICATED_REACHABILITY","status_code":r.status_code,"datasets":[{"id":x.get("id"),"name":x.get("name")} for x in items if isinstance(x,dict)]}
            except Exception: pass
        return {"status":"UNAUTHENTICATED_REACHABILITY" if not self.key else "REACHABILITY","status_code":r.status_code}
    def upload(self, pdfs, expected_host=None):
        import requests
        if not self.key: return {"status":"BLOCKED_AUTH","reason":"MOI_API_KEY absent"}
        if not self.destination_ok(expected_host): return {"status":"BLOCKED_DESTINATION"}
        files=[("files",(p.name,p.read_bytes(),"application/pdf")) for p in pdfs]
        payload={"file_names":[p.name for p in pdfs],"steps":[{"node":"ParseNode","parameters":{}},{"node":"ChunkNode","parameters":{}},{"node":"EmbedNode","parameters":{}}]}
        r=requests.post(self.base+"/v1/genai/pipeline",headers=self.headers(),data={"payload":json.dumps(payload)},files=files,timeout=60,allow_redirects=False)
        if 300<=r.status_code<400: return {"status":"BLOCKED_REDIRECT","status_code":r.status_code}
        try: body=r.json()
        except Exception: body={}
        data=body.get("data") if isinstance(body,dict) else {}
        return {"status_code":r.status_code,"response_keys":list(body) if isinstance(body,dict) else [],"job_id":data.get("job_id") if isinstance(data,dict) else None}
    def query(self,q,dataset_ids,document_ids,expected_host,page_size=10):
        import requests
        if not self.key: return {"status":"BLOCKED_AUTH","reason":"MOI_API_KEY absent"}
        if not self.destination_ok(expected_host): return {"status":"BLOCKED_DESTINATION"}
        payload={"question":q,"dataset_ids":dataset_ids,"document_ids":document_ids,"page_size":page_size}
        t=time.perf_counter(); r=requests.post(self.base+"/byoa/api/v1/retrieval",headers=self.headers(),json=payload,timeout=60,allow_redirects=False)
        if 300<=r.status_code<400: return {"status":"BLOCKED_REDIRECT","status_code":r.status_code}
        try: body=r.json()
        except Exception: body={"raw":r.text[:4000]}
        data=body.get("data",{}) if isinstance(body,dict) else {}
        return {"status_code":r.status_code,"chunks":data.get("chunks",[]),"doc_aggs":data.get("doc_aggs",[]),"latency_ms":round((time.perf_counter()-t)*1000,2),"note":"retrieval only; not Native Explore generated answer"}
    def poll(self, job_id, expected_host):
        import requests
        if not self.key: return {"status":"BLOCKED_AUTH","reason":"MOI_API_KEY absent"}
        if not self.destination_ok(expected_host): return {"status":"BLOCKED_DESTINATION"}
        r=requests.get(self.base+f"/v1/genai/jobs/{job_id}",headers=self.headers(),timeout=30,allow_redirects=False)
        if 300<=r.status_code<400: return {"status":"BLOCKED_REDIRECT","status_code":r.status_code}
        try: body=r.json()
        except Exception: body={}
        data=body.get("data",{}) if isinstance(body,dict) else {}; files=[]
        for f in data.get("files",[]) if isinstance(data,dict) else []:
            if isinstance(f,dict): files.append({k:f.get(k) for k in ("file_id","file_name","file_status","error_message")})
        return {"status_code":r.status_code,"job_status":data.get("status") or data.get("job_status"),"files":files}

def score(run:Path, chunks):
    gold=[json.loads(x) for x in (run/"gold_candidates.jsonl").read_text().splitlines() if x.strip()][0]; texts=[str(c.get("text",c.get("content",""))) for c in chunks]; ev=gold.get("evidence",[])
    haystack=normalized(" ".join(texts)).lower(); hits=[e for e in ev if normalized(e.get("text","")).lower() in haystack]; recall=len(hits)/len(ev) if ev else 0.0
    retrieval=json.loads((run/"retrieval.json").read_text()); backend=retrieval.get("backend","moi_retrieval")
    result={"status":"DIAGNOSTIC_ONLY","reason":"Gold is unreviewed; response adherence is not scored","evidence_hits":len(hits),"evidence_total":len(ev),"normalized_substring_recall":recall,"backend":backend}
    write_json(run/"score.json",result); append_jsonl(run/"manual_explore_run.jsonl",[{"question_id":gold.get("question_id"),"final_response":"PASTE UI RESPONSE","citations":[],"notes":"Manual UI capture; do not use adherence_score."}]); state(run,"score","DONE",diagnostic_status=result["status"],reason=result["reason"],evidence_hits=len(hits),evidence_total=len(ev),normalized_substring_recall=recall,backend=backend)

def demo(args):
    run=prepare(argparse.Namespace(input=args.input,run=args.run)); st=json.loads((run/"state.json").read_text()); st["backend"]="oracle_mock"; write_json(run/"state.json",st); state(run,"retrieval","RUNNING",backend="oracle_mock")
    evidence=json.loads((run/"gold_candidates.jsonl").read_text().splitlines()[0]).get("evidence",[]); manifest=json.loads((run/"corpus_manifest.json").read_text()); chunks=[]
    from pypdf import PdfReader
    for e in evidence:
        d=manifest["documents"][e["document_index"]]; pages=PdfReader(str(run/d["pdf"])); body="\n".join((p.extract_text() or "") for p in pages.pages); needle=e["text"]
        if normalized(needle) in normalized(body): chunks.append({"text":needle,"document_id":d["doc_id"],"score":1.0})
    write_json(run/"retrieval.json",{"backend":"oracle_mock","chunks":chunks,"doc_aggs":[]}); state(run,"retrieval","DONE",chunks=len(chunks),backend="oracle_mock"); score(run,chunks)
    write_json(run/"feasibility.json",{"parquet_to_pdf":"VERIFIED_OFFLINE","pdf_to_moi_processing":"BLOCKED_AUTH","processing_to_byoa_dataset":"BLOCKED_PUBLIC_CONTRACT","moi_retrieval":"BLOCKED_AUTH_DATASET_ID","retrieval_to_score":"VERIFIED_ORACLE_MOCK"})
    return run

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    for name in ("prepare","demo-offline"):
        s=sub.add_parser(name); s.add_argument("--input",default=DEFAULT_INPUT); s.add_argument("--run",default=DEFAULT_RUN if name=="demo-offline" else "runs/prepare")
    s=sub.add_parser("probe"); s.add_argument("--run",default="runs/probe"); s.add_argument("--expected-host",default=None)
    s=sub.add_parser("upload"); s.add_argument("--run",default="runs/prepare"); s.add_argument("--confirm-upload",action="store_true"); s.add_argument("--acknowledge-license-review",action="store_true"); s.add_argument("--expected-host",required=True)
    s=sub.add_parser("poll"); s.add_argument("job_id"); s.add_argument("--run",default="runs/prepare"); s.add_argument("--expected-host",required=True)
    s=sub.add_parser("query"); s.add_argument("--run",default=DEFAULT_RUN); s.add_argument("--dataset-id",action="append",required=True,help="Repeat for multiple dataset IDs"); s.add_argument("--document-id",action="append",default=[],help="Repeat for multiple document IDs"); s.add_argument("--question",default=None); s.add_argument("--expected-host",required=True)
    s=sub.add_parser("score"); s.add_argument("--run",default=DEFAULT_RUN)
    s=sub.add_parser("tui"); s.add_argument("--run",default=DEFAULT_RUN)
    args=p.parse_args()
    if args.cmd=="prepare": prepare(args)
    elif args.cmd=="demo-offline": demo(args)
    elif args.cmd=="probe":
        run=Path(args.run); state(run,"probe","RUNNING")
        try:
            adapter=MoiAdapter(); result=adapter.probe() if (not adapter.key or (args.expected_host and adapter.destination_ok(args.expected_host))) else {"status":"BLOCKED_DESTINATION"}; write_json(run/"probe.json",result); ps=result.get("status"); state(run,"probe","BLOCKED" if str(ps).startswith("BLOCKED") else ("DONE" if ps in ("UNAUTHENTICATED_REACHABILITY","AUTHENTICATED_REACHABILITY") else "FAILED"),probe_status=ps); print(json.dumps(result,ensure_ascii=False))
        except Exception as exc: failed(run,"probe",exc); raise
    elif args.cmd=="upload":
        from urllib.parse import urlparse
        adapter=MoiAdapter(); run=Path(args.run); state(run,"process","RUNNING")
        if not args.confirm_upload or not args.acknowledge_license_review or urlparse(adapter.base).hostname != args.expected_host: result={"status":"BLOCKED_MUTATION_GATE"}; state(run,"process","BLOCKED",reason="mutation gate not satisfied")
        else:
            manifest=json.loads((run/"corpus_manifest.json").read_text()); pdfs=[run/d["pdf"] for d in manifest["documents"]]; result=adapter.upload(pdfs,args.expected_host); state(run,"process",result_stage(result,True),job_id=result.get("job_id"))
        write_json(run/"upload.json",result); print(json.dumps({"status":result.get("status",result.get("status_code"))}))
    elif args.cmd=="poll":
        run=Path(args.run); state(run,"poll","RUNNING"); result=MoiAdapter().poll(args.job_id,args.expected_host); state(run,"poll",result_stage(result)); write_json(run/"poll.json",result); print(json.dumps({"status":result.get("status",result.get("status_code"))}))
    elif args.cmd=="query":
        q=args.question or json.loads((Path(args.run)/"questions.jsonl").read_text().splitlines()[0])["question"]; run=Path(args.run); state(run,"query","RUNNING"); result=MoiAdapter().query(q,args.dataset_id,args.document_id,args.expected_host); result.update({"backend":"moi_retrieval","question":q,"dataset_ids":args.dataset_id,"document_ids":args.document_id,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}); write_json(run/"retrieval.json",result); state(run,"query",result_stage(result)); print(json.dumps({"status":result.get("status",result.get("status_code")),"latency_ms":result.get("latency_ms")}))
    elif args.cmd=="score":
        run=Path(args.run)
        try:
            retrieval=json.loads((run/"retrieval.json").read_text()); score(run,retrieval.get("chunks",[]))
        except Exception as exc: failed(run,"score",exc); raise
    elif args.cmd=="tui": print((Path(args.run)/"state.json").read_text() if (Path(args.run)/"state.json").exists() else "No state yet")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        run_arg=next((sys.argv[i+1] for i,x in enumerate(sys.argv[:-1]) if x=="--run"), None)
        if not run_arg and len(sys.argv) > 1:
            run_arg={
                "demo-offline": DEFAULT_RUN,
                "prepare": "runs/prepare",
                "probe": "runs/probe",
                "upload": "runs/prepare",
                "poll": "runs/prepare",
                "query": DEFAULT_RUN,
                "score": DEFAULT_RUN,
            }.get(sys.argv[1])
        if run_arg:
            run=Path(run_arg); p=run/"state.json"
            if p.exists():
                data=json.loads(p.read_text())
                for name, item in data.get("stages",{}).items():
                    if item.get("status")=="RUNNING": failed(run,name,exc)
        raise
