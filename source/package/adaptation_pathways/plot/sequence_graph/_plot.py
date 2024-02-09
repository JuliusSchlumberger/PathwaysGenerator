from ...graph.sequence_graph import SequenceGraph
from ..colour import PlotColours
from .default import plot as plot_default


def plot_sequence_graph(
    sequence_graph: SequenceGraph,
    title: str = "",
    plot_colours: PlotColours | None = None,
) -> None:
    plot_default(sequence_graph, title, plot_colours)
