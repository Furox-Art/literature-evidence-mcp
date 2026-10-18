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

// DerSimonian-Laird random-effects estimator with Q, I² and sensitivity analyses.
// This is a model calculation, NOT a judgment that studies are exchangeable.
py::dict random_effects_dl(const std::vector<std::pair<double,double>>& studies) {
    if(studies.size()<3 || studies.size()>10000)
        throw std::invalid_argument("3-10000 studies required for random effects");
    Accumulator weight_sum, weighted_sum, squared_weight_sum;
    for(const auto& s:studies) {
        const double effect=s.first, se=s.second;
        if(!std::isfinite(effect)||!std::isfinite(se)||se<=0.0)
            throw std::invalid_argument("finite estimates and positive SE required");
        const double w=1.0/(se*se);
        if(!std::isfinite(w)||w<=0.0||!std::isfinite(w*effect))
            throw std::invalid_argument("numeric weight overflow");
        weight_sum.add(w);weighted_sum.add(w*effect);squared_weight_sum.add(w*w);
    }
    const double sw=weight_sum.value(), swx=weighted_sum.value(), sw2=squared_weight_sum.value();
    if(!std::isfinite(sw)||!std::isfinite(swx)||!std::isfinite(sw2)||sw<=0)
        throw std::invalid_argument("numeric weight sums invalid");
    const double mean=swx/sw;
    Accumulator qsum;
    for(const auto& s:studies) {
        const double z=(s.first-mean)/s.second;
        if(!std::isfinite(z))throw std::invalid_argument("heterogeneity overflow");
        qsum.add(z*z);
    }
    const double q=qsum.value(), df=double(studies.size()-1);
    const double c=sw-sw2/sw;
    if(!std::isfinite(q)||!std::isfinite(c)||c<=0)
        throw std::invalid_argument("heterogeneity denominator invalid");
    const double tau2=std::max(0.0,(q-df)/c);
    const double i2=q>0?std::max(0.0,100.0*(q-df)/q):0.0;
    Accumulator reweights, reweighted;
    for(const auto& s:studies) {
        const double variance=s.second*s.second+tau2;
        const double w=1.0/variance;
        // Because tau² >= 0, random weights cannot exceed previously
        // validated finite inverse-variance weights.
        reweights.add(w);reweighted.add(w*s.first);
    }
    const double w=reweights.value();
    if(!std::isfinite(w)||w<=0)throw std::invalid_argument("invalid random weights");
    const double pooled=reweighted.value()/w, se=std::sqrt(1.0/w);
    constexpr double z=1.959963984540054;
    const double lower=pooled-z*se, upper=pooled+z*se;
    const double pi_half=z*std::sqrt(tau2+se*se);
    // Positive finite weights and finite Q/tau² were validated before
    // intervals; no synthetic inference about coverage probabilities.
    py::dict r;
    r["method"]="DERSIMONIAN_LAIRD_RANDOM_EFFECTS";
    r["number_of_studies"]=studies.size();
    r["q"]=q;r["degrees_of_freedom"]=df;r["i_squared_percent"]=i2;r["tau_squared"]=tau2;
    r["pooled_estimate"]=pooled;r["standard_error"]=se;
    r["ci95_lower"]=lower;r["ci95_upper"]=upper;
    r["approx_prediction95_lower"]=pooled-pi_half;
    r["approx_prediction95_upper"]=pooled+pi_half;
    r["scientific_validity_assessed"]=false;
    r["notice"]="Approximate normal CIs/PI, DL tau²; no Hartung-Knapp, publication bias or study eligibility assessment.";
    return r;
}

py::list leave_one_out_dl(const std::vector<std::pair<double,double>>& studies) {
    if(studies.size()<4||studies.size()>1000)
        throw std::invalid_argument("4-1000 studies needed for leave-one-out");
    py::list reports;
    for(size_t i=0;i<studies.size();++i) {
        std::vector<std::pair<double,double>> subset;
        subset.reserve(studies.size()-1);
        for(size_t j=0;j<studies.size();++j)if(j!=i)subset.push_back(studies[j]);
        py::dict r=random_effects_dl(subset);
        r["excluded_study_index"]=i;
        reports.append(r);
    }
    return reports;
}

PYBIND11_MODULE(literature_evidence_cpp,m){
    m.doc()="Deterministic fixed-effect meta-analysis; no scientific validity claims";
    m.def("fixed_effect", &fixed_effect, py::arg("studies"));
    m.def("random_effects_dl", &random_effects_dl, py::arg("studies"));
    m.def("leave_one_out_dl", &leave_one_out_dl, py::arg("studies"));
}
