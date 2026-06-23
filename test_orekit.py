import orekit_jpype as orekit

orekit.initVM()

from orekit_jpype.pyhelpers import setup_orekit_data
from org.orekit.time import TimeScalesFactory
from org.orekit.frames import FramesFactory
from org.orekit.utils import IERSConventions

setup_orekit_data()

utc = TimeScalesFactory.getUTC()
gcrf = FramesFactory.getGCRF()
itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)

print("Orekit is working")
print("UTC:", utc)
print("GCRF:", gcrf)
print("ITRF:", itrf)