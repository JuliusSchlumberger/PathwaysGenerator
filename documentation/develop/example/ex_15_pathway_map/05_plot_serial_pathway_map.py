"""
Pathway map for serial sequence
===============================
"""

from io import StringIO

import matplotlib.pyplot as plt

from adaptation_pathways.graph import conversion
from adaptation_pathways.io import text
from adaptation_pathways.plot import init_axes
from adaptation_pathways.plot import plot_default_pathway_map as plot


actions, colour_by_action = text.read_actions(
    StringIO(
        """
current #ff4c566a
a #ffbf616a
b #ffd08770
c #ffebcb8b
"""
    )
)
sequences, tipping_point_by_action = text.read_sequences(
    StringIO(
        """
current[1] current
current a
a b
b c
"""
    ),
    actions,
)
sequence_graph = conversion.sequences_to_sequence_graph(sequences)
pathway_map = conversion.sequence_graph_to_pathway_map(sequence_graph)

colour_by_action_name = {
    action.name: colour for action, colour in colour_by_action.items()
}

pathway_map.set_attribute("colour_by_action_name", colour_by_action_name)

_, axes = plt.subplots(layout="constrained")
init_axes(axes)
plot(axes, pathway_map)
plt.show()
