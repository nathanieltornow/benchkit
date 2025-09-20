import matplotlib.pyplot as plt
from cycler import cycler
import numpy as np

colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
hatches = ["/", "\\", "|", "-", "+", "x", "o", "O"]

# Make a combined cycler
plt.rcParams["axes.prop_cycle"] = cycler(color=colors * 2) + cycler(hatch=hatches) + cycler(linestyle=["solid", "dashed"] * 4)

# Example data
x = np.arange(4)
y = np.array([3, 5, 7, 6])

fig, ax = plt.subplots()

bars = ax.errorbar(x, y)

# Hatch needs to be *explicitly applied*; Matplotlib won't auto-apply non-color cycle props
prop_cycler = plt.rcParams["axes.prop_cycle"]
for bar, props in zip(bars, prop_cycler()):
    bar.set_facecolor(props["color"])
    bar.set_hatch(props["hatch"])

plt.savefig("bar_with_hatches.png")
