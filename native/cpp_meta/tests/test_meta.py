import math
import pytest
from literature_evidence_cpp import fixed_effect

def test_symmetric():
 r=fixed_effect([(1.0,.5),(2.0,.5)])
 assert math.isclose(r['pooled_estimate'],1.5,rel_tol=1e-12)
 assert math.isclose(r['standard_error'],.3535533905932738,rel_tol=1e-12)
 assert r['ci95_lower']<1.5<r['ci95_upper']
 assert r['scientific_validity_assessed'] is False
 assert r['number_of_studies']==2

def test_weighting():
 r=fixed_effect([(1.0,.1),(3.0,.2)])
 assert math.isclose(r['pooled_estimate'],1.4,rel_tol=1e-12)

@pytest.mark.parametrize('studies',[
 [],[(1.,.5)],[(1.,0),(2.,.5)],[(1.,-1),(2.,.5)],
 [(float('inf'),1),(2.,.5)],[(float('nan'),1),(2.,.5)],
 [(1,float('nan')),(2.,.5)],[(1,1e-200),(2.,1.)],
 [(1e308,1e-200),(2.,1.)],
])
def test_reject_bad(studies):
 with pytest.raises(ValueError):
  fixed_effect(studies)
