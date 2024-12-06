"""
Pathway map for an example
==========================
"""

from io import StringIO

import matplotlib.pyplot as plt

from adaptation_pathways.graph import SequenceGraph, sequence_graph_to_pathway_map
from adaptation_pathways.io import text
from adaptation_pathways.plot import (
    action_level_by_first_occurrence,
    init_axes,
    plot_classic_pathway_map,
)


actions, colour_by_action = text.read_actions(
    StringIO(
        """
current #ff4c566a
a #ffbf616a
b #ffd08770
c #ffebcb8b
d #ffa3be8c
"""
    )
)
sequences, tipping_point_by_action = text.read_sequences(
    StringIO(
        """
current     current     2030

current     a[1]        2100

current     b[1]        2040
b[1]        a[2]        2100
b[1]        c[2]        2050
c[2]        b[2]        2070
b[2]        a[3]        2100
c[2]        a[4]        2100
c[2]        d[3]        2100
b[1]        d[2]        2100

current     c[1]        2050
c[1]        b[3]        2070
b[3]        a[5]        2100
c[1]        a[6]        2100
c[1]        d[4]        2100

current     d[1]        2100
"""
    ),
    actions,
)
sequence_graph = SequenceGraph(sequences)
pathway_map = sequence_graph_to_pathway_map(sequence_graph)

level_by_action = action_level_by_first_occurrence(sequences)
colour_by_action_name = {
    action.name: colour for action, colour in colour_by_action.items()
}

pathway_map.assign_tipping_points(tipping_point_by_action)
pathway_map.set_attribute("level_by_action", level_by_action)
pathway_map.set_attribute("colour_by_action_name", colour_by_action_name)

arguments = {
    "colour_by_action_name": colour_by_action_name,
}

_, axes = plt.subplots(layout="constrained")
init_axes(axes)
plot_classic_pathway_map(axes, pathway_map, arguments=arguments)
plt.show()
