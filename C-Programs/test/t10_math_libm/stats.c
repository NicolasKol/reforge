#include "mathutil.h"

double mean(const double *data, int n) {
    if (n <= 0) return 0.0;
    double sum = 0.0;
    for (int i = 0; i < n; i++)
        sum += data[i];
    return sum / (double)n;
}

double variance(const double *data, int n) {
    if (n <= 1) return 0.0;
    double m = mean(data, n);
    double ss = 0.0;
    for (int i = 0; i < n; i++) {
        double d = data[i] - m;
        ss += d * d;
    }
    return ss / (double)(n - 1);
}

double stddev(const double *data, int n) {
    return sqrt(variance(data, n));
}

double rms(const double *data, int n) {
    if (n <= 0) return 0.0;
    double ss = 0.0;
    for (int i = 0; i < n; i++)
        ss += data[i] * data[i];
    return sqrt(ss / (double)n);
}

double geometric_mean(const double *data, int n) {
    if (n <= 0) return 0.0;
    double log_sum = 0.0;
    for (int i = 0; i < n; i++) {
        if (data[i] <= 0.0) return 0.0;   /* undefined for non-positive */
        log_sum += log(data[i]);
    }
    return exp(log_sum / (double)n);
}

double normalize_angle(double rad) {
    double twopi = 2.0 * PI;
    double result = fmod(rad, twopi);
    if (result < 0.0) result += twopi;
    return result;
}
