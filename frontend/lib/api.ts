export type Finding = {
  finding_id: string;
  source: { masked_text: string; match_span: [number, number] };
  rule_signal: {
    rule_id: string;
    category: string;
    matched_excerpt: string;
    signal_strength: string;
    rationale: string;
  };
  evidence: Array<{ evidence_id: string; title: string; status: string; authority: string }>;
  assessment?: { summary: string; counter_considerations: string[]; review_questions: string[] };
  verification: { status: string };
};

export type Analysis = {
  id: string;
  document_id: string;
  status: string;
  disposition: string;
  experiment_arm: string;
  result?: { findings: Finding[]; warnings: string[]; clause_count: number };
  progress?: { state: string; percent: number };
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export function reportPdfUrl(analysisId: string): string {
  return `${API_BASE}/api/v1/analyses/${encodeURIComponent(analysisId)}/report.pdf`;
}

export async function uploadAndAnalyze(file: File, arm: "A" | "D"): Promise<Analysis> {
  const form = new FormData();
  form.append("file", file);
  const uploaded = await fetch(`${API_BASE}/api/v1/documents`, { method: "POST", body: form });
  if (!uploaded.ok) throw new Error((await uploaded.json()).detail ?? "업로드에 실패했습니다.");
  const document = await uploaded.json();
  const analyzed = await fetch(`${API_BASE}/api/v1/documents/${document.id}/analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ experiment_arm: arm }),
  });
  if (!analyzed.ok) throw new Error("분석에 실패했습니다.");
  return analyzed.json();
}

export async function waitForAnalysis(analysis: Analysis): Promise<Analysis> {
  let current = analysis;
  for (let attempt = 0; attempt < 60 && current.status === "queued"; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    const response = await fetch(`${API_BASE}/api/v1/analyses/${current.id}`);
    if (!response.ok) throw new Error("분석 상태를 확인하지 못했습니다.");
    current = await response.json();
  }
  if (current.status === "queued") throw new Error("분석 시간이 초과되었습니다. 잠시 후 다시 확인하세요.");
  return current;
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/documents/${documentId}`, { method: "DELETE" });
  if (!response.ok) throw new Error("삭제에 실패했습니다.");
}
