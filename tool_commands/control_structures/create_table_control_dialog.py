from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QAbstractItemView
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.PyQt.QtWidgets import QLabel
from qgis.PyQt.QtWidgets import QPushButton
from qgis.PyQt.QtWidgets import QTableWidget
from qgis.PyQt.QtWidgets import QTableWidgetItem
from qgis.PyQt.QtWidgets import QVBoxLayout
from qgis.PyQt.QtWidgets import QWidget
from ThreeDiToolbox.tool_commands.control_structures import main
from ThreeDiToolbox.utils.constants import DICT_ACTION_TYPES
from ThreeDiToolbox.utils.constants import DICT_TABLE_ID
from ThreeDiToolbox.utils.constants import DICT_TABLE_NAMES
from ThreeDiToolbox.utils.threedi_database import get_database_properties
from ThreeDiToolbox.utils.threedi_database import get_databases

import csv
import logging
import os


logger = logging.getLogger(__name__)

ui_file = Path(__file__).parent / "create_table_control_dialog.ui"
assert ui_file.is_file()
FORM_CLASS, _ = uic.loadUiType(ui_file)


class CreateTableControlDialogWidget(QDialog, FORM_CLASS):
    def __init__(
        self,
        parent=None,
        db_key=None,
        table_control_id=None,
        dockwidget_controlled_structures=None,
    ):
        """Constructor

        Args:
            parent: Qt parent Widget
            (str) db_key: The key of the database. It's a combination of
                          database type (postgres/ spatialite) and
                          name of the database.
            (int) table_control_id: The new id of the control table.
            (QDockWidget) dockwidget_controlled_structures:
                The main dockwidget of the control structures feature.
                This dockwidget is populated with the new table control
                upon pressing OK.
        """
        super().__init__(parent)
        # Show gui
        self.setupUi(self)

        self.table_control_id = table_control_id
        self.dockwidget_controlled_structures = dockwidget_controlled_structures

        self.db_key = db_key
        self.databases = get_databases()
        self.db = get_database_properties(self.db_key)
        self.control_structure = main.ControlledStructures(
            flavor=self.db["db_entry"]["db_type"]
        )
        self.setup_ids()
        self.connect_signals()

    def on_accept(self):
        """Accept and run the Command.run_it method."""
        self.save_table_control()
        self.accept()

    def on_reject(self):
        """Cancel"""
        self.reject()
        logger.debug("Reject")

    def closeEvent(self, event):
        """
        Close widget, called by Qt on close
        :param event: QEvent, close event
        """

        self.buttonbox.accepted.disconnect(self.on_accept)
        self.buttonbox.rejected.disconnect(self.on_reject)

        event.accept()

    def setup_ids(self):
        """Setup the table control id, structure type and structure id."""
        # Set the id of the table control
        self.label_input_rule_id_number.setText(str(self.table_control_id))
        self.control_structure.start_sqalchemy_engine(self.db["db_settings"])
        # Set the structure type
        self.combobox_input_structure_table.clear()
        for key in DICT_TABLE_ID:
            self.combobox_input_structure_table.addItem(key)
        # Set the structure id's
        self.setup_structure_ids()
        # Set the action types of the structures
        self.setup_action_types()

    def setup_structure_ids(self):
        """Setup the structure id's."""
        structure_type = self.combobox_input_structure_table.currentText()
        self.combobox_input_structure_id.clear()
        list_of_structure_ids = self.control_structure.get_attributes(
            table_name="{table_name_base}_view".format(
                table_name_base=DICT_TABLE_NAMES[structure_type]
            ),
            attribute_name=DICT_TABLE_ID[structure_type],
        )
        self.combobox_input_structure_id.addItems(list_of_structure_ids)

    def setup_action_types(self):
        """Setup the action types of the structures."""
        self.combobox_input_action_type.clear()
        structure_type = self.combobox_input_structure_table.currentText()
        self.combobox_input_action_type.addItems(DICT_ACTION_TYPES[structure_type])

    def connect_signals(self):
        """Connect the signals."""
        self.pushbutton_input_rule_add_row.clicked.connect(self.add_row)
        self.pushbutton_input_rule_load_from_csv.clicked.connect(self.load_from_csv)
        self.pushbutton_input_rule_clear.clicked.connect(self.clear_table)
        self.combobox_input_structure_table.activated.connect(self.setup_structure_ids)
        self.combobox_input_structure_table.activated.connect(self.setup_action_types)
        self.buttonbox.accepted.connect(self.on_accept)
        self.buttonbox.rejected.connect(self.on_reject)

    def add_row(self):
        """Add a row to the tablewidget."""
        # The row should be added on the top of the table
        row_position = 0
        self.tablewidget_input_rule_table_control.insertRow(row_position)
        pushbutton_remove_row = QPushButton("Remove")
        pushbutton_remove_row.clicked.connect(self.remove_row)
        self.tablewidget_input_rule_table_control.setCellWidget(
            row_position, 2, pushbutton_remove_row
        )

    def remove_row(self):
        """Remove a row from the tablewidget."""
        tablewidget = self.tablewidget_input_rule_table_control
        row_number = tablewidget.currentRow()
        tablewidget.removeRow(row_number)

    def load_from_csv(self):
        """
        Load data from a csv file in the tablewidget.
        The delimiter of the csv file should be a comma.
        """
        self.clear_table()
        tablewidget = self.tablewidget_input_rule_table_control
        filename = self.get_file("csv")
        if filename:
            csv_file = open(filename, "rb")
            row_number = 0
            action_table = ""
            try:
                reader = csv.reader(csv_file)
                for row in reader:
                    row_position = tablewidget.rowCount()
                    tablewidget.insertRow(row_position)
                    if row_number > 0:
                        action_table += "#"
                    measuring_value = QTableWidgetItem(str(row[0]))
                    action_value = QTableWidgetItem(str(row[1]))
                    tablewidget.setItem(row_position, 0, measuring_value)
                    tablewidget.setItem(row_position, 1, action_value)
                    pushbutton_remove_row = QPushButton("Remove")
                    pushbutton_remove_row.clicked.connect(self.remove_row)
                    tablewidget.setCellWidget(row_position, 2, pushbutton_remove_row)
                    row_number += 1
            finally:
                csv_file.close()

    def get_file(self, file_type):
        """Function to get a file."""
        settings = QSettings("3di_plugin", "qgisplugin")

        try:
            init_path = settings.value("last_used_import_path", type=str)
        except TypeError:
            logger.warning("last_used_import_path is not set, using home dir")
            init_path = os.path.expanduser("~")
        if file_type == "csv":
            filename, __ = QFileDialog.getOpenFileName(
                None, "Select import file", init_path, "Comma-seperated values (*.csv)"
            )
        if filename:
            settings.setValue("last_used_import_path", os.path.dirname(filename))

        return filename

    def clear_table(self):
        """Clear the tablewidget."""
        self.tablewidget_input_rule_table_control.clearContents()
        row_count = self.tablewidget_input_rule_table_control.rowCount()
        for row in range(row_count):
            self.tablewidget_input_rule_table_control.removeRow(0)

    def save_table_control(self):
        """Save the table control in the database."""
        table_control = self.create_table_control_dict()
        self.control_structure.start_sqalchemy_engine(self.db["db_settings"])
        self.control_structure.save_table_control(table_control)
        self.add_table_control_tab_dockwidget()
        self.setup_table_control_tab_dockwidget()

    def create_table_control_dict(self):
        """
        Create a dict for the table control.

        Returns:
            (dict): table_control
        """
        self.control_structure.start_sqalchemy_engine(self.db["db_settings"])
        tablewidget = self.tablewidget_input_rule_table_control
        table_control = {}
        list_of_values_table_control = []
        for row_number in range(tablewidget.rowCount()):
            try:
                measure_value = tablewidget.item(row_number, 0).text()
            except AttributeError:
                logger.exception("measure value cannot be grabbed, using empty string")
                measure_value = ""
            try:
                action_value = tablewidget.item(row_number, 1).text()
            except AttributeError:
                logger.exception("action value cannot be grabbed, using empty string")
                action_value = ""
            list_of_values_table_control.append([measure_value, action_value])
        table_control["action_table"] = self.control_structure.create_action_table(
            list_of_values_table_control
        )
        if self.combobox_input_rule_operator.currentText() == "Bottom up":
            measure_operator = main.RULE_OPERATOR_BOTTOM_UP
        else:
            measure_operator = main.RULE_OPERATOR_TOP_DOWN
        table_control["measure_operator"] = measure_operator
        table_control["target_id"] = self.combobox_input_structure_id.currentText()
        structure_table = self.combobox_input_structure_table.currentText()
        table_control["target_type"] = DICT_TABLE_NAMES.get(structure_table, "")
        table_control["action_type"] = self.combobox_input_action_type.currentText()
        measure_variable = main.MEASURE_VARIABLE_WATERLEVEL
        table_control["measure_variable"] = measure_variable
        table_control["id"] = self.table_control_id
        return table_control

    def add_table_control_tab_dockwidget(self):
        """
        Create a tab for the measure group within the Rule group tab
        in the dockwidget.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        tab.setLayout(layout)

        label_field = QLabel(tab)
        label_field.setGeometry(10, 10, 300, 21)
        label_field.setText(
            "Measure variable: {}".format(
                self.combobox_input_rule_measure_variable.currentText()
            )
        )

        label_field = QLabel(tab)
        label_field.setGeometry(10, 40, 300, 21)
        label_field.setText(
            "Operator: {}".format(self.combobox_input_rule_operator.currentText())
        )

        label_field = QLabel(tab)
        label_field.setGeometry(310, 10, 300, 21)
        label_field.setText(
            "Structure type: {}".format(
                self.combobox_input_structure_table.currentText()
            )
        )

        label_field = QLabel(tab)
        label_field.setGeometry(310, 40, 300, 21)
        label_field.setText(
            "Structure id: {}".format(self.combobox_input_structure_id.currentText())
        )

        label_field = QLabel(tab)
        label_field.setGeometry(310, 70, 741, 21)
        label_field.setText(
            "Action type: {}".format(self.combobox_input_action_type.currentText())
        )

        table_control_table = QTableWidget(tab)
        table_control_table.setGeometry(10, 100, 741, 181)
        table_control_table.insertColumn(0)
        table_control_table.setHorizontalHeaderItem(
            0, QTableWidgetItem("measuring_value")
        )
        table_control_table.insertColumn(1)
        table_control_table.setHorizontalHeaderItem(1, QTableWidgetItem("action_value"))
        table_control_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dockwidget_controlled_structures.table_control_view = table_control_table

        self.dockwidget_controlled_structures.tab_table_control_view.insertTab(
            0, tab, "Table control: {}".format(str(self.table_control_id))
        )

    def setup_table_control_tab_dockwidget(self):
        """
        Setup a tab for the table control in the Rule tab
        in the dockwidget.
        """
        tablewidget_dialog = self.tablewidget_input_rule_table_control
        tablewidget_dockwidget = (
            self.dockwidget_controlled_structures.table_control_view
        )
        list_of_values_table_control = []
        for row_number in range(tablewidget_dialog.rowCount()):
            try:
                measure_value = tablewidget_dialog.item(row_number, 0).text()
            except AttributeError:
                logger.exception("measure value cannot be grabbed, using empty string")
                measure_value = ""
            try:
                action_value = tablewidget_dialog.item(row_number, 1).text()
            except AttributeError:
                logger.exception("action value cannot be grabbed, using empty string")
                action_value = ""
            list_of_values_table_control.append([measure_value, action_value])
            # Populate new tab of "Rule" tab
            row_position = tablewidget_dockwidget.rowCount()
            tablewidget_dockwidget.insertRow(row_position)
            tablewidget_dockwidget.setItem(
                row_position, 0, QTableWidgetItem(measure_value)
            )
            tablewidget_dockwidget.setItem(
                row_position, 1, QTableWidgetItem(action_value)
            )
