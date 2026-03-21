---
name: benchkit-plot
description: Create publication-quality plots for academic papers and presentations using benchkit and matplotlib. Use when the user asks to plot results, create figures, visualize data, or make plots for a paper or thesis.
---

# Publication Plotting Skill

This skill requires the `benchkit` library (`uv add git+https://github.com/nathanieltornow/benchkit@v0.0.1`).

You create publication-quality figures using `benchkit.pplot()` and matplotlib. Every figure you produce must be camera-ready for an academic paper.

## Setup

Always use the benchkit context manager. Choose the right preset and enable LaTeX if the paper uses it:

```python
import benchkit as bk
import matplotlib.pyplot as plt

# For a paper with LaTeX
with bk.pplot(preset="double-column", latex=True):
    fig, ax = plt.subplots()
    ...
analysis.save_figure(fig, plot_name="my-figure")

# For a presentation slide
with bk.pplot(preset="slide"):
    fig, ax = plt.subplots()
    ...
```

### Available presets

| Preset               | Width  | Height | Use case                             |
| -------------------- | ------ | ------ | ------------------------------------ |
| `double-column`      | 180 mm | 45 mm  | Standard paper figure                |
| `double-column-tall` | 180 mm | 70 mm  | Paper figure with legend or subplots |
| `single-column`      | 85 mm  | 55 mm  | Narrow paper figure                  |
| `single-column-tall` | 85 mm  | 85 mm  | Square paper figure                  |
| `slide`              | 254 mm | 143 mm | 16:9 presentation                    |

If no preset fits, compute figsize explicitly:

```python
with bk.pplot(latex=True):
    fig, ax = plt.subplots(figsize=(120 / 25.4, 50 / 25.4))  # 120mm x 50mm
```

## Rules for every figure

### 1. Define a theme mapping

Every figure must have an explicit theme that maps data labels to visual properties. This ensures consistency across related figures:

```python
THEME = {
    "gcc": {"color": "#4477AA", "marker": "o", "linestyle": "-", "hatch": None},
    "clang": {"color": "#EE6677", "marker": "s", "linestyle": "--", "hatch": "//"},
    "rustc": {"color": "#228833", "marker": "^", "linestyle": "-.", "hatch": "\\\\"},
}
```

Rules for themes:

- Colors from the Tol qualitative palette: `#4477AA`, `#EE6677`, `#228833`, `#CCBB44`, `#66CCEE`, `#AA3377`, `#BBBBBB`
- Every series/group gets a unique color AND a unique marker or hatch (for black-and-white printing)
- Reuse the same theme across all figures in one experiment

### 2. Labels and text

- Axis labels: concise, with units in parentheses: `"Compile time (ms)"`, `"Array size ($n$)"`
- No plot titles -- paper figures have captions, not titles. Exception: subplots get short panel labels like `"(a) GCC"`, `"(b) Clang"`
- Use LaTeX math mode for variables and formulas: `r"$\mathcal{O}(n \log n)$"`
- Legend: place inside the axes if it fits without overlapping data. Use `frameon=False` and `loc="best"`. For slim figures, use `ncol=` to make it horizontal

### 3. Bar plots

```python
for i, (label, values) in enumerate(groups.items()):
    style = THEME[label]
    ax.bar(
        x + i * width,
        values,
        width,
        label=label,
        color=style["color"],
        edgecolor="black",
        hatch=style["hatch"],
    )
```

- Always set `edgecolor="black"` for crisp outlines
- Use dense hatches (`//`, `\\\\`, `---`) -- sparse hatches (`/`) disappear in slim figures
- Add value labels on top of bars only when there are few bars (<= 8)
- For grouped bars, compute offsets explicitly with `np.arrange` and `width`

### 4. Line plots

```python
for label, group in df.groupby("config.compiler"):
    style = THEME[label]
    ax.plot(
        group["config.size"],
        group["result.time_ms"],
        label=label,
        color=style["color"],
        marker=style["marker"],
        linestyle=style["linestyle"],
    )
```

- Every line gets a distinct marker AND linestyle (not just color)
- If lines overlap, consider using `alpha=0.8` or offsetting slightly
- For error bars: `ax.fill_between(x, mean-std, mean+std, alpha=0.15, color=style["color"])`

### 5. Subplots

```python
with bk.pplot(preset="double-column-tall", latex=True):
    fig, axes = plt.subplots(1, 3, sharey=True)
    for ax, metric in zip(axes, ["time_ms", "memory_mb", "accuracy"]):
        ...
    axes[0].set_ylabel("Value")  # only leftmost gets ylabel
```

- Share axes when comparing the same metric across conditions
- Only the leftmost subplot gets a y-label; only the bottom gets an x-label
- Use `fig.subplots_adjust(wspace=0.05)` for tight spacing with shared axes

### 6. Save properly

Always save through the analysis handle:

```python
analysis.save_figure(fig, plot_name="compile-comparison")
```

This saves both PDF (for LaTeX `\includegraphics`) and PNG (for README/slides) at 400 DPI with tight bounding box.

## Common patterns

### Speedup / normalized comparison

```python
baseline = df[df["config.variant"] == "baseline"]["result.time_ms"].mean()
df["speedup"] = baseline / df["result.time_ms"]

with bk.pplot(preset="double-column", latex=True):
    fig, ax = plt.subplots()
    ax.axhline(y=1.0, color="gray", linestyle=":", linewidth=0.8, zorder=0)
    for label, group in df.groupby("config.variant"):
        if label == "baseline":
            continue
        style = THEME[label]
        ax.bar(
            label,
            group["speedup"].mean(),
            color=style["color"],
            edgecolor="black",
            hatch=style["hatch"],
        )
    ax.set_ylabel(r"Speedup over baseline ($\times$)")
```

### Scaling / log-log plot

```python
with bk.pplot(preset="single-column", latex=True):
    fig, ax = plt.subplots()
    for label, group in df.groupby("config.method"):
        style = THEME[label]
        ax.loglog(
            group["config.n"],
            group["result.time_ms"],
            label=label,
            color=style["color"],
            marker=style["marker"],
        )
    ax.set_xlabel(r"Problem size ($n$)")
    ax.set_ylabel("Time (ms)")
    ax.legend(frameon=False)
```

### Table as figure (for paper appendix)

When the user asks for a results table, produce it as a formatted pandas DataFrame and save as CSV, not as a matplotlib table. Tables belong in LaTeX, not in figures:

```python
summary = (
    df.groupby(["config.compiler", "config.opt"])
    .agg(
        mean_time=("result.time_ms", "mean"),
        std_time=("result.time_ms", "std"),
    )
    .reset_index()
)
analysis.save_dataframe(summary, "results-table", file_format="csv")
```

## Anti-patterns to avoid

- **No rainbow colormaps.** Use the Tol palette or a sequential single-hue colormap
- **No 3D plots.** They obscure data and don't print well
- **No plot titles.** Paper figures have captions
- **No default matplotlib colors.** Always use the theme
- **No `plt.show()`.** Save through `analysis.save_figure()`
- **No pixel-based sizes.** Always use mm for figure dimensions
- **No legends outside the axes** unless absolutely necessary (wastes space)
