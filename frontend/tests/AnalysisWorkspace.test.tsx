import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisWorkspace } from "@/components/AnalysisWorkspace";

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
});
