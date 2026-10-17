// Low-level geo query engine for the local map store.
// Reads places.tsv (id<TAB>lat<TAB>lng<TAB>name<TAB>address) and answers
// spatial queries with haversine distance — fast linear scan, no deps.
//
// Build:  g++ -O2 -o geo_query geo_query.cpp
// Use:    ./geo_query places.tsv near    <lat> <lng> <radius_km>
//         ./geo_query places.tsv nearest <lat> <lng> <n>
// Output: id<TAB>distance_km<TAB>name<TAB>address   (sorted by distance)
#include <cstdio>
#include <cmath>
#include <string>
#include <vector>
#include <algorithm>
#include <fstream>
#include <sstream>

struct Place { long id; double lat, lng; std::string name, addr; double dist; };

static double haversine(double la1, double lo1, double la2, double lo2) {
    const double R = 6371.0, d2r = M_PI / 180.0;
    double dlat = (la2 - la1) * d2r, dlon = (lo2 - lo1) * d2r;
    double a = std::sin(dlat/2)*std::sin(dlat/2) +
               std::cos(la1*d2r)*std::cos(la2*d2r)*std::sin(dlon/2)*std::sin(dlon/2);
    return R * 2 * std::atan2(std::sqrt(a), std::sqrt(1-a));
}

int main(int argc, char** argv) {
    if (argc < 6) { std::fprintf(stderr, "usage: geo_query <tsv> near|nearest <lat> <lng> <r|n>\n"); return 1; }
    std::string tsv = argv[1], mode = argv[2];
    double qlat = std::stod(argv[3]), qlng = std::stod(argv[4]);
    double param = std::stod(argv[5]);

    std::ifstream in(tsv);
    if (!in) { std::fprintf(stderr, "cannot open %s\n", tsv.c_str()); return 1; }

    std::vector<Place> hits;
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::stringstream ss(line);
        std::string sid, slat, slng, name, addr;
        std::getline(ss, sid, '\t'); std::getline(ss, slat, '\t');
        std::getline(ss, slng, '\t'); std::getline(ss, name, '\t');
        std::getline(ss, addr, '\t');
        Place p;
        try { p.id = std::stol(sid); p.lat = std::stod(slat); p.lng = std::stod(slng); }
        catch (...) { continue; }
        p.name = name; p.addr = addr;
        p.dist = haversine(qlat, qlng, p.lat, p.lng);
        hits.push_back(p);
    }
    std::sort(hits.begin(), hits.end(), [](const Place&a, const Place&b){ return a.dist < b.dist; });

    if (mode == "near") {
        for (auto& p : hits) if (p.dist <= param)
            std::printf("%ld\t%.3f\t%s\t%s\n", p.id, p.dist, p.name.c_str(), p.addr.c_str());
    } else { // nearest N
        int n = (int)param, c = 0;
        for (auto& p : hits) { if (c++ >= n) break;
            std::printf("%ld\t%.3f\t%s\t%s\n", p.id, p.dist, p.name.c_str(), p.addr.c_str()); }
    }
    return 0;
}
