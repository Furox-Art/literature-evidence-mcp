// Fixed-effect inverse-variance meta-analysis from user-supplied estimates.
// The calculation does not judge bias, study eligibility or causal inference.
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py=pybind11;
struct Accumulator {
    double total=0.0;
    double correction=0.0;
    void add(double value){
        double t=total+value;
        if(std::abs(total)>=std::abs(value)) correction+=(total-t)+value;
        else correction+=(value-t)+total;
        total=t;
    }
    double value() const {return total+correction;}
};

py::dict fixed_effect(const std::vector<std::pair<double,double>>& studies) {
    if(studies.size()<2 || studies.size()>10000) throw std::invalid_argument("2-10000 studies required");
    Accumulator weights, weighted;
    for(const auto& item:studies){
        auto effect=item.first; auto se=item.second;
        if(!std::isfinite(effect)|| !std::isfinite(se) || se<=0.0) throw std::invalid_argument("finite effect and positive finite standard error required");
        auto w=1.0/(se*se);
        if(!std::isfinite(w) || w<=0.0) throw std::invalid_argument("weight overflow");
        weights.add(w); weighted.add(w*effect);
    }
    double sumw=weights.value(), sumwx=weighted.value();
    if(!std::isfinite(sumw)||!std::isfinite(sumwx) || sumw<=0.0) throw std::invalid_argument("numeric overflow");
    double pooled=sumwx/sumw;
    double pooled_se=std::sqrt(1.0/sumw);
    constexpr double z=1.959963984540054;
    if(!std::isfinite(pooled)||!std::isfinite(pooled_se)) throw std::invalid_argument("numeric overflow");
    py::dict result;
    result["method"]="FIXED_EFFECT_INVERSE_VARIANCE";
    result["number_of_studies"]=studies.size();
    result["pooled_estimate"]=pooled;
    result["standard_error"]=pooled_se;
    result["ci95_lower"]=pooled-z*pooled_se;
    result["ci95_upper"]=pooled+z*pooled_se;
    result["scientific_validity_assessed"]=false;
    result["notice"]="Assumes a common effect and correctly supplied independent study estimates/SEs; heterogeneity and bias not assessed.";
    return result;
}
PYBIND11_MODULE(literature_evidence_cpp,m){
    m.doc()="Deterministic fixed-effect meta-analysis; no scientific validity claims";
    m.def("fixed_effect", &fixed_effect, py::arg("studies"));
}
