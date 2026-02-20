#include <iostream>
#include <sstream>
#include <chrono>
#include <vector>
#include <string>
#include <cmath>

#include <nlohmann/json.hpp>
#include <libnest2d/libnest2d.hpp>

namespace nl = nlohmann;

using namespace libnest2d;

static constexpr double PI = 3.14159265358979323846;

int main(int argc, char* argv[]) {
  try {
    std::cin.tie(nullptr);
    std::ios_base::sync_with_stdio(false);
    std::stringstream ss;
    ss << std::cin.rdbuf();
    std::string input = ss.str();

    if (input.empty()) {
      std::cerr << "nest_engine: empty input\n";
      return 1;
    }

    nl::json j = nl::json::parse(input);

    std::string units = j.value("units", "mm");
    double scale = 1000.0;  // mm -> integer units (1mm = 1000)
    if (units == "mm") scale = 1000.0;
    else if (units == "m") scale = 1e6;

    double bin_w = j["bin"]["width"].get<double>();
    double bin_h = j["bin"]["height"].get<double>();
    using Coord = TCoord<PointImpl>;
    Coord scaled_bin_w = static_cast<Coord>(std::round(bin_w * scale));
    Coord scaled_bin_h = static_cast<Coord>(std::round(bin_h * scale));

    double spacing = 0.0;
    std::vector<double> rotations_deg = {0.0, 90.0};
    int timeout_ms = 0;
    if (j.contains("options")) {
      const auto& opt = j["options"];
      spacing = opt.value("spacing", 0.0);
      if (opt.contains("rotations") && opt["rotations"].is_array())
        rotations_deg = opt["rotations"].get<std::vector<double>>();
      timeout_ms = opt.value("timeout_ms", 0);
    }
    Coord scaled_spacing = static_cast<Coord>(std::round(spacing * scale));

    std::vector<Item> items;
    std::vector<std::string> instance_ids;

    for (const auto& part : j["parts"]) {
      std::string id = part["id"].get<std::string>();
      int qty = part.value("qty", 1);
      const auto& polygon = part["polygon"];
      if (!polygon.is_array() || polygon.empty()) continue;

      PathImpl path;
      for (const auto& pt : polygon) {
        double x = pt[0].get<double>();
        double y = pt[1].get<double>();
        path.push_back(PointImpl{
          static_cast<Coord>(std::round(x * scale)),
          static_cast<Coord>(std::round(y * scale))});
      }
      if (path.size() >= 2 && (getX(path.front()) != getX(path.back()) || getY(path.front()) != getY(path.back())))
        path.push_back(path.front());

      PolygonImpl shape = shapelike::create<PolygonImpl>(path);

      for (int i = 0; i < qty; ++i) {
        items.push_back(Item(shape));
        instance_ids.push_back(id + "#" + std::to_string(i + 1));
      }
    }

    if (items.empty()) {
      std::cerr << "nest_engine: no parts to nest\n";
      return 1;
    }

    Box bin(scaled_bin_w, scaled_bin_h);

    NestConfig<NfpPlacer, FirstFitSelection> cfg;
    cfg.placer_config.rotations.clear();
    for (double deg : rotations_deg)
      cfg.placer_config.rotations.push_back(deg * PI / 180.0);
    if (cfg.placer_config.rotations.empty())
      cfg.placer_config.rotations = {0.0, PI/2, PI, 3*PI/2};

    auto start_time = std::chrono::steady_clock::now();
    NestControl ctl;
    if (timeout_ms > 0) {
      ctl.stopcond = [start_time, timeout_ms]() {
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now() - start_time).count();
        return elapsed >= timeout_ms;
      };
    }

    size_t bins_used = nest(items.begin(), items.end(), bin, scaled_spacing, cfg, ctl);

    auto end_time = std::chrono::steady_clock::now();
    long runtime_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();

    double total_area = 0;
    for (const auto& it : items)
      total_area += it.area();
    double bin_area = static_cast<double>(bin.width()) * static_cast<double>(bin.height());
    double utilization = (bins_used > 0 && bin_area > 0)
      ? (total_area / (static_cast<double>(bins_used) * bin_area)) : 0.0;

    nl::json out;
    out["bins_used"] = bins_used;
    out["placements"] = nl::json::array();
    for (size_t i = 0; i < items.size(); ++i) {
      const auto& it = items[i];
      auto tr = it.translation();
      double rot_deg = static_cast<double>(Degrees(it.rotation()));
      out["placements"].push_back({
        {"instance_id", instance_ids[i]},
        {"bin", it.binId()},
        {"x", static_cast<double>(getX(tr)) / scale},
        {"y", static_cast<double>(getY(tr)) / scale},
        {"rotation", rot_deg}
      });
    }
    out["metrics"] = {
      {"runtime_ms", runtime_ms},
      {"utilization", utilization}
    };

    std::cout << out.dump() << std::endl;
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "nest_engine: " << e.what() << std::endl;
    return 1;
  }
}
