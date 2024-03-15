import copy
import sys
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QObject, Slot
from PySide6.QtUiTools import QUiLoader

import adaptation_pathways as ap

from ..action import Action
from ..graph import (
    PathwayGraph,
    PathwayMap,
    SequenceGraph,
    pathway_graph_to_pathway_map,
    sequence_graph_to_pathway_graph,
    sequences_to_sequence_graph,
)
from ..io import sqlite as dbms
from ..plot import (
    pathway_graph_node_colours,
    pathway_map_edge_colours,
    pathway_map_node_colours,
    plot_default_pathway_graph,
    plot_default_pathway_map,
    plot_default_sequence_graph,
    sequence_graph_node_colours,
)
from ..plot.colour import (
    Colour,
    PlotColours,
    argb_to_hex,
    default_edge_colours,
    default_label_colour,
    default_node_edge_colours,
    default_nominal_palette,
    hex_to_argb,
)
from .model.action import ActionModel
from .model.sequence import SequenceModel
from .path import Path
from .widget.pathway_graph import PathwayGraphWidget
from .widget.pathway_map import PathwayMapWidget
from .widget.sequence_graph import SequenceGraphWidget


# pylint: disable=too-many-instance-attributes, too-many-locals


loader = QUiLoader()


try:
    from ctypes import windll  # type: ignore

    my_app_id = f"nl.adaptation_pathways.pathway_generator.{ap.__version__}"
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)
except ImportError:
    pass


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def configure_colour_dialog(palette):
    for idx, colour in enumerate(palette):
        QtWidgets.QColorDialog.setCustomColor(idx, QtGui.QColor.fromRgbF(*colour))


def show_error_message(parent, message):
    QtWidgets.QMessageBox.critical(parent, "Error", message)


# def exception_handler(type_, value, traceback):
#     QtWidgets.QMessageBox.critical(None, "Error", f"{value}")
#     sys.stderr.write(f"{traceback}")


class MainUI(QObject):  # Not a widget
    def __init__(self):
        # pylint: disable=too-many-statements
        super().__init__()
        self.name = "Adaptation Pathway Generator"
        self.version = f"{ap.__version__}"

        self._current_palette = default_nominal_palette()
        configure_colour_dialog(self._current_palette)

        self.ui = loader.load(Path.ui("main_window.ui"), None)
        self.ui.show()

        self.log_widget = loader.load(Path.ui("log_widget.ui"), None)
        self.log_widget.browser.insertHtml(
            "<i>Below you may see messages that have been logged while using the application. When "
            "interactively defining the graphs underlying the pathway map, they may temporarily "
            "end up in an inconsistent state. Instead of continuously reporting errors, they "
            "are logged here. If you know what you are doing, you do not need to read them, "
            "but they may be useful case of surprising behaviour.</i><hr/>"
        )

        self.ui.installEventFilter(self)

        self.ui.action_open.setIcon(QtGui.QIcon(Path.icon("folder-open-table.png")))
        self.ui.action_save.setIcon(QtGui.QIcon(Path.icon("disk.png")))
        self.ui.action_save_as.setIcon(QtGui.QIcon(Path.icon("disk.png")))

        self.ui.action_open.triggered.connect(self._open_dataset)
        self.ui.action_save.triggered.connect(
            lambda: self._save_dataset(self.dataset_pathname)
        )
        # self.ui.action_save.setEnabled(self.dataset_pathname != "")
        self.ui.action_save_as.triggered.connect(self._save_as_dataset)
        self.ui.action_toggle_log_window.toggled.connect(self.log_widget.setVisible)
        self.ui.action_about.triggered.connect(self._show_about_dialog)

        self.ui.table_actions.customContextMenuRequested.connect(
            self._on_actions_table_context_menu
        )
        self.ui.table_actions.doubleClicked.connect(
            lambda idx: self._edit_action(idx.row())
        )

        self.ui.table_sequences.customContextMenuRequested.connect(
            self._on_sequences_table_context_menu
        )
        self.ui.table_sequences.doubleClicked.connect(
            lambda idx: self._edit_sequence(idx.row())
        )
        self.ui.table_sequences.verticalHeader().setSectionsMovable(True)
        self.ui.table_sequences.verticalHeader().setDragEnabled(True)
        self.ui.table_sequences.verticalHeader().setDragDropMode(
            QtWidgets.QAbstractItemView.InternalMove
        )

        self.colour_by_action: dict[Action, Colour] = {}

        self.actions: list[list] = []
        self.action_model = ActionModel(self.actions, self.colour_by_action)
        self.ui.table_actions.setModel(self.action_model)

        self.sequences: list[list[Action]] = []
        self.sequence_model = SequenceModel(self.sequences, self.colour_by_action)
        self.ui.table_sequences.setModel(self.sequence_model)

        self.action_model.rowsAboutToBeRemoved.connect(
            self._actions_about_to_be_removed
        )
        self.action_model.rowsRemoved.connect(self._actions_removed)
        self.sequence_model.rowsAboutToBeRemoved.connect(
            self._sequences_about_to_be_removed
        )
        self.sequence_model.rowsRemoved.connect(self._sequences_removed)

        self.sequence_graph_widget = SequenceGraphWidget(
            parent=None, width=5, height=4, dpi=100
        )
        self.ui.plot_tab_widget.addTab(self.sequence_graph_widget, "Sequence graph")

        self.pathway_graph_widget = PathwayGraphWidget(
            parent=None, width=5, height=4, dpi=100
        )
        self.ui.plot_tab_widget.addTab(self.pathway_graph_widget, "Pathway graph")

        self.pathway_map_widget = PathwayMapWidget(
            parent=None, width=5, height=4, dpi=100
        )
        self.ui.plot_tab_widget.addTab(self.pathway_map_widget, "Pathway map")

        self.ui.editor_tab_widget.setCurrentIndex(0)
        self.ui.plot_tab_widget.setCurrentIndex(0)
        self.ui.splitter.setSizes((100, 200))

        self.plot_widgets = [
            self.sequence_graph_widget,
            self.pathway_graph_widget,
            self.pathway_map_widget,
        ]

        self.dataset_pathname = ""
        self.data_changed = False

        self._set_dataset_pathname(self.dataset_pathname)
        self._set_data_changed(self.data_changed)

    def eventFilter(self, object_, event):
        if (
            isinstance(object_, QtWidgets.QMainWindow)
            and event.type() == QtCore.QEvent.Close
        ):
            if not self._handle_unsaved_changes():
                event.ignore()
            else:
                # Only when the log window is hidden will the application exit
                self.log_widget.hide()
                return True

        return False

    def _plot_sequence_graph(self, sequence_graph: SequenceGraph) -> None:
        colour_by_action_name = {
            action.name: colour for action, colour in self.colour_by_action.items()
        }
        plot_colours = PlotColours(
            sequence_graph_node_colours(sequence_graph, colour_by_action_name),
            default_edge_colours(sequence_graph),
            default_node_edge_colours(sequence_graph),
            default_label_colour(),
        )

        self.sequence_graph_widget.axes.clear()
        plot_default_sequence_graph(
            self.sequence_graph_widget.axes, sequence_graph, plot_colours=plot_colours
        )
        self.sequence_graph_widget.draw()

    def _plot_pathway_graph(self, pathway_graph: PathwayGraph) -> None:
        colour_by_action_name = {
            action.name: colour for action, colour in self.colour_by_action.items()
        }
        plot_colours = PlotColours(
            pathway_graph_node_colours(pathway_graph, colour_by_action_name),
            default_edge_colours(pathway_graph),
            default_node_edge_colours(pathway_graph),
            default_label_colour(),
        )

        self.pathway_graph_widget.axes.clear()
        plot_default_pathway_graph(
            self.pathway_graph_widget.axes, pathway_graph, plot_colours=plot_colours
        )
        self.pathway_graph_widget.draw()

    def _plot_pathway_map(self, pathway_map: PathwayMap) -> None:
        colour_by_action_name = {
            action.name: colour for action, colour in self.colour_by_action.items()
        }
        plot_colours = PlotColours(
            pathway_map_node_colours(pathway_map, colour_by_action_name),
            pathway_map_edge_colours(pathway_map, colour_by_action_name),
            default_node_edge_colours(pathway_map),
            default_label_colour(),
        )

        self.pathway_map_widget.axes.clear()
        plot_default_pathway_map(
            self.pathway_map_widget.axes, pathway_map, plot_colours=plot_colours
        )
        self.pathway_map_widget.draw()

    def _log_message(self, message: str) -> None:
        self.log_widget.browser.insertHtml(f"<b>{timestamp()}</b>: {message}<br/>")

        # If the log browser is not visible, notify the user that there is something to look at

        # Update the status bar
        self.ui.statusBar().showMessage("Messages have been logged")

    def _clear_plots(self):
        for plot_widget in self.plot_widgets:
            plot_widget.axes.clear()
            plot_widget.draw()

    def _update_plots(self) -> None:
        try:
            sequences = [(record[0], record[1]) for record in self.sequences]
            sequence_graph = sequences_to_sequence_graph(sequences)
            pathway_graph = sequence_graph_to_pathway_graph(sequence_graph)
            pathway_map = pathway_graph_to_pathway_map(pathway_graph)

            self._plot_sequence_graph(sequence_graph)
            self._plot_pathway_graph(pathway_graph)
            self._plot_pathway_map(pathway_map)
        except LookupError as exception:
            self._clear_plots()
            self._log_message(str(exception))

    @Slot()
    def _open_dataset(self):
        if not self._handle_unsaved_changes():
            return

        dataset_pathname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.ui, "Open Dataset", "", "Datasets (*.apw);;All files (*.*)"
        )

        if dataset_pathname:
            actions, sequences, colour_by_action = dbms.read_dataset(dataset_pathname)

            self.colour_by_action.clear()
            self.colour_by_action.update(
                {
                    action: hex_to_argb(colour)
                    for action, colour in colour_by_action.items()
                }
            )

            self._set_dataset_pathname(dataset_pathname)

            self.actions.clear()
            self.actions.extend([action] for action in actions)
            # TODO try to use the model logic for this
            self.ui.table_actions.model().layoutChanged.emit()

            self.sequences.clear()
            self.sequences.extend(
                [[sequence[0], sequence[1]] for sequence in sequences]
            )
            # TODO try to use the model logic for this
            self.ui.table_sequences.model().layoutChanged.emit()

            self._update_plots()

    def _save_dataset(self, dataset_pathname: str):
        """
        Save all data to a dataset
        """
        # self.dataset_pathname = dataset_pathname

        # assert self.dataset_pathname != ""

        assert dataset_pathname != ""

        actions = [record[0] for record in self.actions]
        sequences = [(sequence[0], sequence[1]) for sequence in self.sequences]
        colour_by_action = {
            action: argb_to_hex(colour)
            for action, colour in self.colour_by_action.items()
        }

        try:
            dbms.write_dataset(actions, sequences, colour_by_action, dataset_pathname)
            self._set_dataset_pathname(dataset_pathname)
            self._set_data_changed(False)
        except RuntimeError as exception:
            show_error_message(self.ui, f"{exception}")
            self._set_dataset_pathname("")

    def _save_as_dataset(self):
        """
        Save all data to a dataset, but first ask for a name
        """
        # TODO Being able to set a default suffix would be nice. If the user types a name
        #      without one now, the file is silently overwritten.
        dataset_pathname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.ui, "Save Dataset", "", "Datasets (*.apw);;All files (*.*)"
        )

        # Nothing happens in case the user cancels
        if dataset_pathname:
            self._save_dataset(dataset_pathname)

    def _handle_unsaved_changes(self):
        handled = True

        if self.data_changed:
            button_pressed = QtWidgets.QMessageBox.question(
                self.ui,
                "Unsaved changes",
                "Do you want to save your changes?",
                QtWidgets.QMessageBox.Save
                | QtWidgets.QMessageBox.Discard
                | QtWidgets.QMessageBox.Cancel,
            )

            if button_pressed == QtWidgets.QMessageBox.Save:
                if self.dataset_pathname == "":
                    self._save_as_dataset()
                else:
                    self._save_dataset(self.dataset_pathname)
            elif button_pressed == QtWidgets.QMessageBox.Cancel:
                handled = False

        return handled

    def _on_actions_table_context_menu(self, pos):
        context = QtWidgets.QMenu(self.ui.table_actions)
        action_idx = self.ui.table_actions.rowAt(pos.y())

        edit_action_action = QtGui.QAction("Edit action...", self.ui.table_actions)
        edit_action_action.triggered.connect(lambda: self._edit_action(action_idx))
        context.addAction(edit_action_action)
        edit_action_action.setEnabled(action_idx != -1)

        remove_action_action = QtGui.QAction("Remove action", self.ui.table_actions)
        remove_action_action.triggered.connect(
            lambda: self._remove_actions(action_idx, 1)
        )
        context.addAction(remove_action_action)
        remove_action_action.setEnabled(action_idx != -1)

        add_action_action = QtGui.QAction("Add action...", self.ui.table_actions)
        add_action_action.triggered.connect(self._add_action)
        context.addAction(add_action_action)

        clear_actions_action = QtGui.QAction("Clear actions", self.ui.table_actions)
        clear_actions_action.triggered.connect(
            lambda: self._remove_actions(0, len(self.actions))
        )
        context.addAction(clear_actions_action)
        clear_actions_action.setEnabled(len(self.actions) > 0)

        context.exec(self.ui.table_actions.viewport().mapToGlobal(pos))

    def _add_action(self):
        current_nr_actions = len(self.actions)
        name = f"Name{current_nr_actions + 1}"
        colour_idx = current_nr_actions % len(self._current_palette)
        colour = self._current_palette[colour_idx]

        action = Action(name)
        self.colour_by_action[action] = colour
        self.actions.append([action])
        self._set_data_changed(True)

        self.ui.table_actions.model().layoutChanged.emit()
        self._edit_action(len(self.actions) - 1, default_values=True)

    def _edit_action(self, idx, default_values=False):
        action_record = self.actions[idx]
        action = action_record[0]

        dialog = loader.load(Path.ui("edit_action_dialog.ui"), self.ui)
        dialog.name_edit.setText(action.name)

        if default_values:
            # Nudge the user to immediately change the default name
            dialog.name_edit.selectAll()

        palette = dialog.select_colour_button.palette()
        role = dialog.select_colour_button.backgroundRole()
        colour = QtGui.QColor.fromRgbF(*self.colour_by_action[action])
        palette.setColor(role, colour)
        dialog.select_colour_button.setPalette(palette)
        dialog.select_colour_button.setAutoFillBackground(True)

        new_colour = colour

        def select_colour():
            """
            Allow the user to select a colour
            """
            nonlocal new_colour

            new_colour = QtWidgets.QColorDialog.getColor(initial=colour)

            if not new_colour.isValid():
                new_colour = colour

            palette.setColor(role, new_colour)
            dialog.select_colour_button.setPalette(palette)

        dialog.select_colour_button.clicked.connect(select_colour)
        dialog.adjustSize()

        if dialog.exec():
            new_name = dialog.name_edit.text()

            something_changed = new_name != action.name or new_colour != colour

            if something_changed:
                # self.actions[idx][0].name = new_name
                # self.actions[idx][1] = new_colour.getRgbF()

                self._set_data_changed(True)

                self.colour_by_action[action] = new_colour.getRgbF()
                self.actions[idx] = [action]

                old_name = action.name

                for sequence in self.sequences:
                    from_action, to_action = sequence
                    if from_action.name == old_name:
                        from_action.name = new_name
                    if to_action.name == old_name:
                        to_action.name = new_name

                self.actions[idx][0].name = new_name

                # new_action_tuple = (
                #     Action(new_name),
                #     new_colour.getRgbF(),
                #     new_tipping_point,
                # )
                # self.actions[idx] = new_action_tuple
                # TODO try to use the model logic for this
                self.ui.table_actions.model().layoutChanged.emit()
                self.ui.table_sequences.model().layoutChanged.emit()
                self._update_plots()

    def _remove_actions(self, idx, nr_actions):
        # TODO button = QtWidgets.QMessageBox.warning(
        # TODO     self.ui,
        # TODO     "Warning",
        # TODO     "Removing actions will also remove associated sequences.\n" "Are you sure?",
        # TODO     QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
        # TODO )

        # TODO if button == QtWidgets.QMessageBox.Yes:
        # TODO     self.ui.table_actions.model().removeRows(
        # TODO         idx, nr_actions, parent=QtCore.QModelIndex()
        # TODO     )

        # TODO Warning or not? Don't annoy people
        self.ui.table_actions.model().removeRows(idx, nr_actions, QtCore.QModelIndex())

    def _actions_about_to_be_removed(
        self, parent, first_idx, last_idx
    ):  # pylint: disable=unused-argument
        # Handle the situation that actions are about to be removed from the table:
        # - Sequences that involve the actions must be removed as well
        # - Colours associated with the actions must be removed
        actions = [record[0] for record in self.actions[first_idx : last_idx + 1]]
        action_names = [action.name for action in actions]
        sequences = [
            record
            for record in self.sequences
            if record[0].name in action_names or record[1].name in action_names
        ]

        for sequence in sequences:
            self.ui.table_sequences.model().removeRow(self.sequences.index(sequence))

        for action in actions:
            del self.colour_by_action[action]

    def _actions_removed(
        self, parent, first_idx, last_idx
    ):  # pylint: disable=unused-argument
        self._update_plots()

    def _sequences_about_to_be_removed(
        self, parent, first_idx, last_idx
    ):  # pylint: disable=unused-argument
        pass

    def _sequences_removed(
        self, parent, first_idx, last_idx
    ):  # pylint: disable=unused-argument
        self._update_plots()

    def _on_sequences_table_context_menu(self, pos):
        context = QtWidgets.QMenu(self.ui.table_sequences)
        sequence_idx = self.ui.table_sequences.rowAt(pos.y())

        edit_sequence_action = QtGui.QAction(
            "Edit sequence...", self.ui.table_sequences
        )
        edit_sequence_action.triggered.connect(
            lambda: self._edit_sequence(sequence_idx)
        )
        context.addAction(edit_sequence_action)
        edit_sequence_action.setEnabled(sequence_idx != -1)

        remove_sequence_action = QtGui.QAction(
            "Remove sequence", self.ui.table_sequences
        )
        remove_sequence_action.triggered.connect(
            lambda: self.ui.table_sequences.model().removeRow(sequence_idx)
        )
        context.addAction(remove_sequence_action)
        remove_sequence_action.setEnabled(sequence_idx != -1)

        add_sequence_action = QtGui.QAction("Add sequence...", self.ui.table_sequences)
        add_sequence_action.triggered.connect(self._add_sequence)
        context.addAction(add_sequence_action)
        add_sequence_action.setEnabled(len(self.actions) > 1)

        clear_sequences_action = QtGui.QAction(
            "Clear sequences", self.ui.table_sequences
        )
        clear_sequences_action.triggered.connect(
            lambda: self.ui.table_sequences.model().removeRows(
                0, len(self.sequences), parent=QtCore.QModelIndex()
            )
        )
        context.addAction(clear_sequences_action)
        clear_sequences_action.setEnabled(len(self.sequences) > 0)

        context.exec(self.ui.table_sequences.viewport().mapToGlobal(pos))

    def _add_sequence(self):
        assert len(self.actions) > 1
        from_action = self.actions[0][0]
        to_action = self.actions[1][0]

        self.sequences.append([from_action, to_action])
        # TODO try to use the model logic for this
        self.ui.table_sequences.model().layoutChanged.emit()
        self._edit_sequence(len(self.sequences) - 1)
        self._update_plots()

    def _edit_sequence(self, idx):  # pylint: disable=too-many-statements
        sequence_record = self.sequences[idx]
        from_action, to_action = sequence_record

        dialog = loader.load(Path.ui("edit_sequence_dialog.ui"), self.ui)

        dialog.start_pathway_radio_button.toggled.connect(
            dialog.from_action_start_combo_box.setEnabled
        )
        dialog.continue_pathway_radio_button.toggled.connect(
            dialog.from_action_continue_combo_box.setEnabled
        )

        actions = [record[0] for record in self.actions]
        sequences = self.sequences
        to_actions = [record[1] for record in self.sequences]

        start_of_pathway = from_action not in to_actions
        continuation_of_pathway = not start_of_pathway

        dialog.start_pathway_radio_button.setChecked(start_of_pathway)
        dialog.from_action_start_combo_box.setEnabled(start_of_pathway)
        dialog.continue_pathway_radio_button.setChecked(continuation_of_pathway)
        dialog.from_action_continue_combo_box.setEnabled(continuation_of_pathway)

        # To start a pathway, one of the existing actions must be selected
        # To end a sequence, one of the existing actions must be selected
        for action in actions:
            image = QtGui.QPixmap(16, 16)
            image.fill(QtGui.QColor.fromRgbF(*self.colour_by_action[action]))
            dialog.from_action_start_combo_box.addItem(image, action.name)
            dialog.to_action_combo_box.addItem(image, action.name)

        # To continue a pathway, one of the defined sequences must be selected
        for sequence in sequences:
            from_action_, to_action_ = sequence
            image = QtGui.QImage(16, 16, QtGui.QImage.Format_RGB32)
            painter = QtGui.QPainter(image)
            painter.fillRect(
                0, 0, 8, 16, QtGui.QColor.fromRgbF(*self.colour_by_action[from_action_])
            )
            painter.fillRect(
                8, 0, 8, 16, QtGui.QColor.fromRgbF(*self.colour_by_action[to_action_])
            )
            painter.end()
            dialog.from_action_continue_combo_box.addItem(
                QtGui.QPixmap.fromImage(image),
                f"{from_action_.name} - {to_action_.name}",
            )

        if start_of_pathway:
            dialog.from_action_start_combo_box.setCurrentIndex(
                next(
                    idx
                    for idx, action in enumerate(actions)
                    if action.name == sequence_record[0].name
                )
            )
        else:
            # Find sequence that ends in current from_action
            from_sequence = next(
                sequence for sequence in sequences if sequence[1] == from_action
            )
            dialog.from_action_continue_combo_box.setCurrentIndex(
                sequences.index(from_sequence)
            )

        dialog.to_action_combo_box.setCurrentIndex(
            next(
                idx
                for idx, action in enumerate(actions)
                if action.name == sequence_record[1].name
            )
        )

        dialog.adjustSize()

        if dialog.exec():
            start_of_pathway = dialog.start_pathway_radio_button.isChecked()
            continuation_of_pathway = not start_of_pathway

            if start_of_pathway:
                action_idx = dialog.from_action_start_combo_box.currentIndex()

                if actions[action_idx] == from_action:
                    # Nothing changed
                    new_from_action = from_action
                else:
                    # Deep copy the existing action
                    new_from_action = copy.deepcopy(actions[action_idx])
                    self.colour_by_action[new_from_action] = self.colour_by_action[
                        actions[action_idx]
                    ]
            else:
                sequence_idx = dialog.from_action_continue_combo_box.currentIndex()

                # Reference to the existing action
                new_from_action = sequences[sequence_idx][1]

            action_idx = dialog.to_action_combo_box.currentIndex()

            if actions[action_idx] == to_action:
                # Nothing changed
                new_to_action = to_action
            else:
                # Deep copy the existing action
                new_to_action = copy.deepcopy(actions[action_idx])
                self.colour_by_action[new_to_action] = self.colour_by_action[
                    actions[action_idx]
                ]

            something_changed = (
                new_from_action != from_action or new_to_action != to_action
            )

            if something_changed:
                # TODO try to use the model logic for this
                self.sequences[idx] = [new_from_action, new_to_action]
                self.ui.table_sequences.model().layoutChanged.emit()
                self._update_plots()

    def _reformat_window_title(self):
        dataset_pathname = (
            self.dataset_pathname if self.dataset_pathname != "" else "<unnamed>"
        )
        changed = "*" if self.data_changed else ""

        self.ui.setWindowTitle(
            f"{self.name} - {self.version}: {dataset_pathname}{changed}"
        )

    def _set_dataset_pathname(self, dataset_pathname: str) -> None:
        self.dataset_pathname = dataset_pathname

        self.ui.action_save.setEnabled(self.dataset_pathname != "")
        self._reformat_window_title()

    def _set_data_changed(self, data_changed: bool) -> None:
        self.data_changed = data_changed

        self._reformat_window_title()

    @Slot()
    def _show_about_dialog(self):
        dialog = loader.load(Path.ui("about_dialog.ui"), self.ui)
        dialog.setWindowTitle(f"About {self.name}")
        dialog.text.setText("*Meh*!")
        dialog.show()


def application():
    # sys.excepthook = exception_handler
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(Path.icon("icon.svg")))
    _ = MainUI()
    app.exec()

    return 0
