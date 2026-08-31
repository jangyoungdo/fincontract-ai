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
});
