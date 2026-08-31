import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisWorkspace } from "@/components/AnalysisWorkspace";
import { reportPdfUrl } from "@/lib/api";

describe("AnalysisWorkspace", () => {
  it("shows the legal boundary and upload contract", () => {
    render(<AnalysisWorkspace />);
    expect(screen.getByText("법률 판단이 아닌 검토 보조")).toBeInTheDocument();
    expect(screen.getByLabelText("계약서 파일")).toHaveAttribute("accept", ".txt,.pdf,.docx");
    expect(screen.getByRole("button", { name: "분석 시작" })).toBeDisabled();
  });

  it("does not invent a bank comparison when no verified dataset exists", () => {
    render(<AnalysisWorkspace />);
    expect(screen.getAllByText("은행 비교").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/순위나 추천은 표시하지 않습니다/).length).toBeGreaterThan(0);
  });

  it("builds a safe PDF report download URL", () => {
    expect(reportPdfUrl("analysis/id")).toBe(
      "http://127.0.0.1:8000/api/v1/analyses/analysis%2Fid/report.pdf",
    );
  });
});
