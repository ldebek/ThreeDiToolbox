# -*- coding: utf-8 -*-

"""
/***************************************************************************
 DWFCalculator
                                 A QGIS plugin
 Calculate DWF
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2021-01-27
        copyright            : (C) 2021 by Nelen en Schuurmans
        email                : emile.debadts@nelen-schuurmans.nl
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = "Nelen en Schuurmans"
__date__ = "2021-01-27"
__copyright__ = "(C) 2021 by Nelen en Schuurmans"

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = "$Format:%H$"

from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingException
from qgis.core import QgsProcessingParameterFile
from qgis.core import QgsProcessingParameterFileDestination
from qgis.core import QgsProcessingParameterProviderConnection
from qgis.core import QgsProcessingParameterString
from qgis.core import QgsProviderConnectionException
from qgis.core import QgsProviderRegistry
from qgis.PyQt.QtCore import QCoreApplication

import csv
import datetime
import logging
import sqlite3


# Default values
DWF_FACTORS = [
    [0, 0.03],
    [1, 0.015],
    [2, 0.01],
    [3, 0.01],
    [4, 0.005],
    [5, 0.005],
    [6, 0.025],
    [7, 0.080],
    [8, 0.075],
    [9, 0.06],
    [10, 0.055],
    [11, 0.05],
    [12, 0.045],
    [13, 0.04],
    [14, 0.04],
    [15, 0.035],
    [16, 0.035],
    [17, 0.04],
    [18, 0.055],
    [19, 0.08],
    [20, 0.07],
    [21, 0.055],
    [22, 0.045],
    [23, 0.04],
]

# DWF per person = 120 l/inhabitant / 1000 = 0.12 m3/inhabitant
DWF_PER_PERSON = 0.12


def get_dwf_factors_from_file(file_path):

    dwf_factors = []
    with open(file_path) as csv_file:
        reader = csv.reader(csv_file, delimiter=",")
        for row in reader:
            print(row)
            dwf_factors += [[int(row[0]), float(row[1])]]

    return dwf_factors


def start_time_and_duration_to_dwf_factors(start_time, duration, dwf_factors):

    starting_time = datetime.datetime.strptime(start_time, "%H:%M:%S")

    # First timestep at 0 seconds
    current_hour = starting_time.hour
    dwf_factor_per_timestep = [[0, dwf_factors[starting_time.hour % 24][1]]]

    for second in range(1, duration + 1):
        time = starting_time + datetime.timedelta(seconds=second)
        if time.hour != current_hour:
            dwf_factor_per_timestep.append([second, dwf_factors[time.hour % 24][1]])
        elif second == duration:
            dwf_factor_per_timestep.append([second, dwf_factors[time.hour % 24][1]])

        current_hour = time.hour

    return dwf_factor_per_timestep


def read_dwf_per_node(spatialite_path):

    """Obtains the DWF per connection node per second a 3Di model sqlite-file."""

    conn = sqlite3.connect(spatialite_path)
    c = conn.cursor()

    # Create empty list that holds total 24h dry weather flow per node
    dwf_per_node_per_second = []

    # Create a table that contains nr_of_inhabitants per connection_node and iterate over it
    for row in c.execute(
        """
        WITH imp_surface_count AS
            ( SELECT impsurf.id, impsurf.nr_of_inhabitants / COUNT(impmap.impervious_surface_id) AS nr_of_inhabitants
             FROM v2_impervious_surface impsurf, v2_impervious_surface_map impmap
             WHERE impsurf.nr_of_inhabitants IS NOT NULL AND impsurf.nr_of_inhabitants != 0
             AND impsurf.id = impmap.impervious_surface_id GROUP BY impsurf.id),
        inhibs_per_node AS (
            SELECT impmap.impervious_surface_id, impsurfcount.nr_of_inhabitants, impmap.connection_node_id
            FROM imp_surface_count impsurfcount, v2_impervious_surface_map impmap
            WHERE impsurfcount.id = impmap.impervious_surface_id)
        SELECT ipn.connection_node_id, SUM(ipn.nr_of_inhabitants)
        FROM inhibs_per_node ipn GROUP BY ipn.connection_node_id
        """
    ):
        dwf_per_node_per_second.append([row[0], row[1] * DWF_PER_PERSON / 3600])

    conn.close()

    return dwf_per_node_per_second


def generate_dwf_lateral_json(spatialite_filepath, start_time, duration, dwf_factors):

    dwf_on_each_node = read_dwf_per_node(spatialite_filepath)
    dwf_factor_per_timestep = start_time_and_duration_to_dwf_factors(
        start_time=start_time, duration=duration, dwf_factors=dwf_factors
    )
    # Initialize list that will hold JSON
    dwf_list = []

    # Generate JSON for each connection node
    for dwf_node in dwf_on_each_node:
        dwf_per_timestep = """"""
        for row in dwf_factor_per_timestep:
            dwf_per_timestep = (
                dwf_per_timestep + str(row[0]) + "," + str(dwf_node[1] * row[1]) + "\n"
            )

        dwf_per_timestep = dwf_per_timestep[:-1]
        dwf_list.append(
            {
                "offset": 0,
                "interpolate": 0,
                "values": dwf_per_timestep,
                "units": "m3/s",
                "connection_node": dwf_node[0],
            }
        )

    return dwf_list


def dwf_json_to_csv(dwf_list, output_csv_file):

    with open(output_csv_file, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        for i, row in enumerate(dwf_list):
            lat_id = i
            connection_node_id = row["connection_node"]
            timeseries = row["values"]
            writer.writerow([str(lat_id), str(connection_node_id), timeseries])


def str_to_seconds(time_str):
    """Get Seconds from time."""
    m, s = time_str.split(":")
    return int(m) * 60 + int(s)


class DWFCalculatorAlgorithm(QgsProcessingAlgorithm):

    OUTPUT = "OUTPUT"
    INPUT = "INPUT"

    def initAlgorithm(self, config):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """

        # We add the input vector features source. It can have any kind of
        # geometry.
        self.addParameter(
            QgsProcessingParameterProviderConnection(
                name=self.INPUT,
                description=self.tr("Input spatialite (.sqlite)"),
                provider="spatialite",
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                "start_time", self.tr("Start time of day (HH:MM:SS)"), "00:00:00"
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                "duration", self.tr("Simulation duration (seconds)")
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                "dwf_progress_file",
                self.tr("DWF progress file (.csv)"),
                extension="csv",
                defaultValue=None,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT, self.tr("Output CSV"), "csv(*.csv)"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """

        start_time = self.parameterAsString(parameters, "start_time", context)
        duration = self.parameterAsDouble(parameters, "duration", context)
        connection_name = self.parameterAsConnectionName(
            parameters, self.INPUT, context
        )
        output_csv = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        dwf_factor_input = self.parameterAsFile(
            parameters, "dwf_progress_file", context
        )

        try:
            md = QgsProviderRegistry.instance().providerMetadata("spatialite")
            conn = md.createConnection(connection_name)
        except QgsProviderConnectionException:
            logging.exception("Error setting up connection to spatialite")
            raise QgsProcessingException(
                self.tr("Could not retrieve connection details for {}").format(
                    connection_name
                )
            )

        spatialite_filename = conn.uri()[8:-1]

        if dwf_factor_input:
            dwf_factors = get_dwf_factors_from_file(dwf_factor_input)
        else:
            dwf_factors = DWF_FACTORS

        dwf_list = generate_dwf_lateral_json(
            spatialite_filepath=spatialite_filename,
            start_time=start_time,
            duration=int(duration),
            dwf_factors=dwf_factors,
        )

        dwf_json_to_csv(dwf_list=dwf_list, output_csv_file=output_csv)

        return {self.OUTPUT: output_csv}

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return "DWFCalculator"

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr("DWF Calculator")

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr("Dry weather flow")

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return "dwf"

    def shortHelpString(self):

        help_string = """
        Calculate dry weather flow on connection nodes for a given model schematisation and simulation settings. Produces a formatted csv that can be used as a 1d lateral in the 3Di API Client.
        Input spatialite: valid spatialite containing the schematisation of a 3Di model. \n
        Start time of day: at which hour of the day the simulation is started (HH:MM:SS). \n
        Simulation duration: amount of time the simulation is run (seconds). \n
        DWF progress file:  timeseries that contains the fraction of the maximum dry weather flow at each hour of the day. Formatted as follows:\n
        '0, 0.03'\n
        '1, 0.015'\n
        ...
        '23, 0.04'\n
        Defaults to a pattern specified by Rioned.
        Output CSV: csv file to which the output 1d laterals are saved. This will be the input used by the API Client.
        """

        return self.tr(help_string)

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return DWFCalculatorAlgorithm()
