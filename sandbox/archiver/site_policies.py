# -*- coding: utf-8 -*-

# This is the ESS policies.py used to enforce policies for archiving PVs
#
# It was created from policies.py from NSLS-II and SLAC
# (https://github.com/slacmshankar/epicsarchiverap/blob/master/src/sitespecific/slacdev/classpathfiles/policies.py)
#
# At a very high level, when users request PVs to be archived, the mgmt web app samples the PV to determine event rate and other parameters.
# In addition, various fields of the PV like .NAME, .ADEL, .MDEL, .RTYP etc are also obtained
# These are passed to this python script as a dictionary argument to a method called determinePolicy
# The variable name in the python environment for this information is 'pvInfo' (so use other variable names etc.).
# The method is expected to use this information to make decisions on various archiving parameters.
# The result is expected to be another dictionary that is placed into the variable called "pvPolicy".
# Optionally, fields in addition to the VAL field that are to be archived with the PV are passed in as a property of pvPolicy called 'archiveFields'
# If the user overrides the policy, this is communicated in the pvinfo as a property called 'policyName'
#
# In addition, this script must communicate the list of available policies to the JVM as another method called getPolicyList which takes no arguments.
# The results of this method is placed into a variable called called 'pvPolicies'.
# The dictionary is a name to description mapping - the description is used in the UI; the name is what is communicated to determinePolicy as a user override
#
# In addition, this script must communicate the list of fields that are to be archived as part of the stream in a method called getFieldsArchivedAsPartOfStream.
# The results of this method is placed into a list variable called called 'pvStandardFields'.

import logging

logging.basicConfig(
    filename="/var/log/tomcat/archappl-policy.log",
    format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.DEBUG,
)

# We use the environment variables ARCHAPPL_XXXX_TERM_FOLDER to determine the location of the STS/MTS/LTS in the appliance
# They should be defined in the tomcat.conf file.
SHORTTERMSTORE_PLUGIN_URL = "pb://localhost?name=STS&rootFolder=${ARCHAPPL_SHORT_TERM_FOLDER}&partitionGranularity=PARTITION_DAY&hold=7&gather=1&consolidateOnShutdown=true"
MEDIUMTERMSTORE_PLUGIN_URL = "pb://localhost?name=MTS&rootFolder=${ARCHAPPL_MEDIUM_TERM_FOLDER}&partitionGranularity=PARTITION_MONTH&hold=12&gather=1"
LONGTERMSTORE_PLUGIN_URL = "pb://localhost?name=LTS&rootFolder=${ARCHAPPL_LONG_TERM_FOLDER}&partitionGranularity=PARTITION_YEAR"
LONGTERMSTORE_BLACKHOLE_PLUGIN_URL = "blackhole://localhost?name=LTS"
DEFAULT_DATASTORES = [
    SHORTTERMSTORE_PLUGIN_URL,
    MEDIUMTERMSTORE_PLUGIN_URL,
    LONGTERMSTORE_PLUGIN_URL,
]


LEVEL_ALARM_FIELDS = ["HIHI", "HIGH", "LOW", "LOLO", "LOPR", "HOPR", "ADEL", "EGU"]
LEVEL_SETTING_FIELDS = ["DRVH", "DRVL"]
BINARY_FIELDS = ["ZNAM", "ONAM"]
MOTOR_FIELDS = ["ACCL", "ATHM", "BACC", "BDST", "BVEL", "CNEN", "DCOF", "DHLM",
                "DIFF", "DINP", "DIR", "DLLM", "DLY", "DMOV", "DOL", "DRBV",
                "DVAL", "ERES", "FOF", "FOFF", "FRAC", "HHSV", "HLM", "HLS",
                "HLSV", "HOMF", "HOMR", "HSV", "HVEL", "ICOF", "IGSET", "INIT",
                "JAR", "JOGF", "JOGR", "JVEL", "LLM", "LLS", "LLSV", "LOCK",
                "LSV", "LVIO", "MDEL", "MISS", "MOVN", "MRES", "MSTA", "NTM",
                "NTMF", "OFF", "OMSL", "OUT", "PCOF", "POST", "PREC", "PREM",
                "RBV", "RCNT", "RDBD", "RDBL", "RDIF", "REP", "RHLS", "RINP",
                "RLLS", "RLNK", "RLV", "RMOD", "RMP", "RRBV", "RRES", "RTRY",
                "RVAL", "RVEL", "S", "SBAK", "SBAS", "SET", "SMAX", "SPDB",
                "SPMG", "SREV", "SSET", "STOO", "STOP", "STUP", "SUSE", "SYNC",
                "TDIR", "TWF", "TWR", "TWV", "UEIP", "UREV", "URIP", "VAL",
                "VBAS", "VELO", "VMAX", "VOF", "ACCS", "ACCU", "CARD", "RSTM",
                "VERS"]

ALL_FIELDS = list(set(LEVEL_ALARM_FIELDS + LEVEL_SETTING_FIELDS + BINARY_FIELDS))

REC_FIELDS = {
    "calc": LEVEL_ALARM_FIELDS,
    "calcout": LEVEL_ALARM_FIELDS,
    "ai": LEVEL_ALARM_FIELDS,
    "ao": LEVEL_ALARM_FIELDS + LEVEL_SETTING_FIELDS,
    "longin": LEVEL_ALARM_FIELDS,
    "longout": LEVEL_ALARM_FIELDS + LEVEL_SETTING_FIELDS,
    "dfanout": LEVEL_ALARM_FIELDS,
    "sub": LEVEL_ALARM_FIELDS,
    "longin": LEVEL_ALARM_FIELDS,
    "bi": BINARY_FIELDS,
    "bo": BINARY_FIELDS,
    "motor": LEVEL_ALARM_FIELDS + MOTOR_FIELDS
}


def getFieldsArchivedAsPartOfStream():
    """Return a list of fields that will be archived as part of every PV.

    The data for these fields will be included in the stream for the PV.
    We also make an assumption that the data type for these fields is the same as that of the .VAL field
    """
    return ALL_FIELDS


def getPolicyList():
    """Generate a list of policy names

    This is used to feed the dropdown in the UI.
    """
    return {
        "default": "The default policy (archive at 14Hz) with Monitor",
        "1Hz": "Archive data at about 1Hz with Monitor",
        "1HzSCAN": "Archive data at about 1Hz with Scan",
        "14HzSCAN": "Archive data at about 14Hz with Scan",
        "3DaysMTSOnly": "Store data for 3 days up to the MTS only",
    }


def determinePolicy(pv_info):
    """Return the policy to apply for the given PV

    pv_info is a dict with the information computed by the engine about the PV.
    It includes:
        - dbrtype -- The ArchDBRType of the PV
        - eventRate -- The sampled event rate in events per second.
        - storageRate -- The sampled storage in bytes per seconds.
        - aliasName -- The value of the .NAME field for aliases
        - policyName -- If the user has overridden the policy when requesting archiving, this is the name of the policy

    The output should be a dict with the following keys:
        - samplingPeriod -- The sampling period to use for this PV. Shall be a float (not an int!).
        - samplingMethod -- The sampling method to use for this PV [SCAN|MONITOR|DONT_ARCHIVE]
        - policyName -- The name of the policy that was used for this PV.
        - controlPV -- Another PV that can be used to conditionally archive this PV.
        - dataStores -- An array of StoragePlugin URL's that can be parsed by StoragePluginURLParser. These form the stages of data storage for this PV.
        - archiveFields -- A optional array of fields that will be archived as part of archiving the .VAL field for this PV.
        - appliance -- Optional; assign this PV to this appliance. This is a string and is the identity of the appliance you want to assign this PV to.
    """
    logging.debug("determinePolicy for %s", pv_info)
    pv_policy = {
        "samplingPeriod": 0.07,
        "samplingMethod": "MONITOR",
        "policyName": pv_info.get("policyName", "default"),
        "dataStores": DEFAULT_DATASTORES,
        "archiveFields": REC_FIELDS.get(pv_info.get("RTYP", ""), []),
    }
    is_waveform = pv_info.get("dbrtype", "").startswith("DBR_WAVEFORM")

    if is_waveform and pv_info["storageRate"] > 560000:   # 5000 doubles points at 14Hz
        logging.warning(
            "Waveform %s has a too high storage rate (%s). Refusing to archive.",
            pv_info["pvName"],
            pv_info["storageRate"],
        )
        pv_policy["samplingMethod"] = "DONT_ARCHIVE"
    if pv_policy["policyName"] == "1Hz" or (is_waveform and pv_info["storageRate"] > 12000): # Around 100 doubles points at 14Hz
        pv_policy["samplingPeriod"] = 1.0
        pv_policy["policyName"] = "1Hz"
    if pv_policy["policyName"] == "1HzSCAN":
        pv_policy["samplingPeriod"] = 1.0
        pv_policy["policyName"] = "1HzSCAN"
        pv_policy["samplingMethod"] = "SCAN"
    if pv_policy["policyName"] == "14HzSCAN":
        pv_policy["policyName"] = "14HzSCAN"
        pv_policy["samplingMethod"] = "SCAN"
    elif pv_policy["policyName"] == "3DaysMTSOnly":
        pv_policy["dataStores"] = [
            SHORTTERMSTORE_PLUGIN_URL,
            # We want to store 3 days worth of data in the MTS.
            "pb://localhost?name=MTS&rootFolder=${ARCHAPPL_MEDIUM_TERM_FOLDER}&partitionGranularity=PARTITION_WEEK&hold=4&gather=1",
            LONGTERMSTORE_BLACKHOLE_PLUGIN_URL,
        ]

    logging.info("policy for %s: %s", pv_info["pvName"], pv_policy)
    return pv_policy
