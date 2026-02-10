#include "mathutil.h"

double deg_to_rad(double deg) {
    return deg * PI / 180.0;
}

double rad_to_deg(double rad) {
    return rad * 180.0 / PI;
}

double triangle_area(double a, double b, double angle_rad) {
    return 0.5 * a * b * sin(angle_rad);
}

void sincos_table(double start_deg, double end_deg, double step,
                  double *sin_out, double *cos_out, int *count, int max) {
    *count = 0;
    for (double d = start_deg; d <= end_deg && *count < max; d += step) {
        double r = deg_to_rad(d);
        sin_out[*count] = sin(r);
        cos_out[*count] = cos(r);
        (*count)++;
    }
}

/* Fourier-ish sum: sum of sin(k*x)/k for k=1..harmonics */
double wave_sum(double x, int harmonics) {
    double sum = 0.0;
    for (int k = 1; k <= harmonics; k++) {
        sum += sin((double)k * x) / (double)k;
    }
    return sum;
}
