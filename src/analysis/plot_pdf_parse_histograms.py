"""Draw 3 images (whitespace / hangul / broken-char ratio). Each image has one histogram
per PDF parser, showing how the ratio is distributed across documents.

Usage: uv run python src/plot_pdf_parse_histograms.py   (needs parsed_detail_pdf.csv; page-level data)
Output: data/parsed/plots/hist_<metric>.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from build_pdf_parse_detail import DETAIL_CSV_PATH
from run_parse_documents import PARSED_OUTPUT_DIR, PDF_PARSERS

PLOT_OUTPUT_DIR = PARSED_OUTPUT_DIR / "plots"
RATIO_METRICS = {
    "whitespace_ratio": "공백 비율",
    "hangul_ratio": "한글 비율",
    "broken_char_ratio": "깨진 문자 비율",
}
HISTOGRAM_BIN_COUNT = 20
PARSER_COLORS = {"pdfplumber": "#4C78A8", "pymupdf": "#F58518", "pypdf": "#54A24B"}


def load_pdf_detail_dataframe() -> pd.DataFrame:
    return pd.read_csv(DETAIL_CSV_PATH, encoding="utf-8-sig")


def draw_ratio_histograms_per_parser(detail_dataframe: pd.DataFrame, metric_name: str, metric_label: str) -> None:
    figure, axes = plt.subplots(1, len(PDF_PARSERS), figsize=(15, 4), sharex=True, sharey=True)

    # shared x range so the three parsers are directly comparable
    all_values = pd.concat([detail_dataframe[f"{parser}_{metric_name}"] for parser in PDF_PARSERS]).dropna()
    value_range = (0.0, max(all_values.max(), 0.01) * 1.05)

    # one histogram per parser
    for axis, parser_name in zip(axes, PDF_PARSERS):
        parser_values = detail_dataframe[f"{parser_name}_{metric_name}"].dropna()
        axis.hist(parser_values, bins=HISTOGRAM_BIN_COUNT, range=value_range,
                  color=PARSER_COLORS[parser_name], edgecolor="white")
        axis.set_title(f"{parser_name} (n={len(parser_values)}, median={parser_values.median():.3f})")
        axis.set_xlabel(metric_label)
        axis.grid(axis="y", alpha=0.3)
    if metric_name == "broken_char_ratio":
        axes[0].set_yscale("log")  # almost all pages are ~0, so a log axis keeps the rare broken pages visible
    axes[0].set_ylabel("페이지 수")

    # save the figure
    figure.suptitle(f"PDF 파서별 {metric_label} 분포 (페이지 단위)")
    figure.tight_layout()
    PLOT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(PLOT_OUTPUT_DIR / f"hist_{metric_name}.png", dpi=150)
    plt.close(figure)


def main() -> None:
    plt.rcParams["font.family"] = ["AppleGothic", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    detail_dataframe = load_pdf_detail_dataframe()
    for metric_name, metric_label in RATIO_METRICS.items():
        draw_ratio_histograms_per_parser(detail_dataframe, metric_name, metric_label)

    print(f"saved {len(RATIO_METRICS)} images -> {PLOT_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
