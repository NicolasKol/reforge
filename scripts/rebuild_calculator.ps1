$source = Get-Content "C:\Users\nico_\Documents\UNI\Thesis\Source\reforge\C-Programs\simple_programs\Calculator.c" -Raw

$body = @{
    name = "Calculator"
    source_code = $source
    test_category = "simple_programs"
    language = "c"
    compilers = @("gcc")
    optimizations = @("O0", "O2", "O3")
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Uri "http://localhost:8080/builder/synthetic" -Method Post -Body $body -ContentType "application/json"
