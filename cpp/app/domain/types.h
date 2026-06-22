#pragma once

namespace imgsli::app::domain {

struct Point {
  double x = 0.0;
  double y = 0.0;
};

struct Color {
  int r = 255;
  int g = 255;
  int b = 255;
  int a = 255;
};

struct Rect {
  int x = 0;
  int y = 0;
  int w = 0;
  int h = 0;
};

}  // namespace imgsli::app::domain
