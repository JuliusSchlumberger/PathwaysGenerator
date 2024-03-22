"""
Sequence graph for an example
=============================
"""

from io import StringIO

import matplotlib.pyplot as plt

from adaptation_pathways.graph import conversion
from adaptation_pathways.io import text
from adaptation_pathways.plot import init_axes
from adaptation_pathways.plot import plot_default_sequence_graph as plot


actions, colour_by_action = text.read_actions(
    StringIO(
        """
current
a
b
c
d
e
f
"""
    )
)
sequences, tipping_point_by_action = text.read_sequences(
    StringIO(
        """
current[1] current
current    a
a          e[1]
current    b
b          f[1]
current    c
c          f[2]
current    d
d          f[3]
f[1]       e[2]
f[2]       e[3]
f[3]       e[4]
"""
    )
)
sequence_graph = conversion.sequences_to_sequence_graph(sequences)

_, axes = plt.subplots(layout="constrained")
init_axes(axes)
plot(axes, sequence_graph)
plt.show()
