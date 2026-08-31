"use client";

import { FormEvent, useState } from "react";
import { Analysis, deleteDocument, reportPdfUrl, uploadAndAnalyze, waitForAnalysis } from "@/lib/api";

const stageLabels = ["문서 확인", "개인정보 보호", "위험 신호 탐색", "근거·결과 검토"];

/**
 * Own the complete non-technical review workflow: upload, queued progress,
 * grounded findings, PDF export, and explicit source deletion.
 */
export function AnalysisWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [arm, setArm] = useState<"A" | "D">("D");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    // Reset stale results before starting a new document lifecycle.
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(""); setAnalysis(null);
    try {
      const created = await uploadAndAnalyze(file, arm);
      setAnalysis(created);
      setAnalysis(await waitForAnalysis(created));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "처리 중 오류가 발생했습니다."); }
    finally { setBusy(false); }
  }

  async function remove() {
    // Clear local state only after the backend confirms encrypted-file deletion.
    if (!analysis) return;
    await deleteDocument(analysis.document_id);
    setAnalysis(null); setFile(null);
  }

  return <main>
    <section className="hero">
      <div><p className="eyebrow">금융 계약서 Vertical AI 실험</p><h1>FinContract AI</h1><p>위험 신호와 확인 가능한 근거를 나란히 보여주는 계약 검토 보조 도구</p></div>
      <span className="notice">법률 판단이 아닌 검토 보조</span>
    </section>

    <nav className="stages" aria-label="분석 단계">
      {stageLabels.map((label, index) => <span key={label} className={analysis || index === 0 ? "active" : ""}>{index + 1}. {label}</span>)}
    </nav>

    <section className="panel">
      <h2>계약서 업로드</h2><p className="muted">TXT, PDF, DOCX · 최대 10MB · 원문은 분석 후 삭제할 수 있습니다.</p>
      <form onSubmit={submit}>
        <label className="drop"><input aria-label="계약서 파일" type="file" accept=".txt,.pdf,.docx" onChange={event => setFile(event.target.files?.[0] ?? null)} /><b>{file?.name ?? "파일을 선택하세요"}</b><span>마스킹 전 원문은 외부 모델이나 ChromaDB로 보내지 않습니다.</span></label>
        <div className="actions"><label>실험군 <select value={arm} onChange={event => setArm(event.target.value as "A" | "D")}><option value="A">A · 규칙 기준선</option><option value="D">D · mock 분석·검증</option></select></label><button disabled={!file || busy}>{busy ? "분석 중…" : "분석 시작"}</button></div>
      </form>{error && <p role="alert" className="error">{error}</p>}
    </section>

    {analysis && <section aria-live="polite">
      <div className="panel summary"><div><span>상태</span><b>{analysis.disposition}</b></div><div><span>조항</span><b>{analysis.result?.clause_count ?? 0}</b></div><div><span>검토 신호</span><b>{analysis.result?.findings.length ?? 0}</b></div>{analysis.status === "completed" && <a className="report-link" href={reportPdfUrl(analysis.id)} download>PDF 리포트</a>}<button className="secondary" onClick={remove}>원문·결과 삭제</button></div>
      {(analysis.result?.warnings ?? []).map(warning => <p className="warning" key={warning}>{warning}</p>)}
      {(analysis.result?.findings ?? []).map(finding => <article className="finding" key={finding.finding_id}>
        <header><div><span className="tag">{finding.rule_signal.signal_strength}</span><h3>{finding.rule_signal.category}</h3></div><span>검증 {finding.verification.status}</span></header>
        <div className="columns"><div><h4>마스킹된 조항</h4><blockquote>{finding.source.masked_text}</blockquote><p>{finding.assessment?.summary ?? finding.rule_signal.rationale}</p></div><div><h4>법적 근거 후보</h4>{finding.evidence.map(item => <div className="evidence" key={item.evidence_id}><b>{item.title}</b><small>{item.status} · {item.authority}</small></div>)}<h4>확인 질문</h4><ul>{(finding.assessment?.review_questions ?? []).map(question => <li key={question}>{question}</li>)}</ul></div></div>
      </article>)}
      <section className="panel limitations"><h2>데이터 제공 범위</h2><p><b>원문 뷰어</b>는 개인정보를 마스킹한 검토 조항만 표시합니다. 원문 전체나 마스킹 전 텍스트는 화면·검색·외부 모델로 전송하지 않습니다.</p><p><b>은행 비교</b>는 검증된 공개·허가 비교 데이터가 아직 없어 순위·추천·비교 결과를 제공하지 않습니다.</p><p><b>리포트</b>는 PDF와 JSON 형식의 검토 보조 자료이며, 법률 판단이나 상품 추천이 아닙니다.</p></section>
    </section>}
    {!analysis && <section className="panel limitations"><h2>은행 비교</h2><p>검증된 공개·허가 비교 데이터가 아직 없습니다. 따라서 순위나 추천은 표시하지 않습니다.</p></section>}
  </main>;
}
