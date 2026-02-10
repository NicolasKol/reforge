#ifndef MATHUTIL_H
#define MATHUTIL_H

#include <stdio.h>
#include <math.h>

#define PI 3.14159265358979323846

/* trig.c */
double deg_to_rad(double deg);
double rad_to_deg(double rad);
double triangle_area(double a, double b, double angle_rad);
void   sincos_table(double start_deg, double end_deg, double step,
                    double *sin_out, double *cos_out, int *count, int max);
double wave_sum(double x, int harmonics);

/* stats.c */
double mean(const double *data, int n);
double variance(const double *data, int n);
double stddev(const double *data, int n);
double rms(const double *data, int n);
double geometric_mean(const double *data, int n);
double normalize_angle(double rad);

#endif /* MATHUTIL_H */
