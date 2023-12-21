"""
Pathway graph for diverging pathways
====================================
"""
from io import StringIO

import matplotlib.pyplot as plt

from adaptation_pathways.graph import (
    plot_pathway_graph,
    read_sequences,
    sequence_graph_to_pathway_graph,
)


sequence_graph = read_sequences(
    StringIO(
        """
current a
current b
current c
"""
    )
)
pathway_graph = sequence_graph_to_pathway_graph(sequence_graph)

plot_pathway_graph(pathway_graph)
plt.show()