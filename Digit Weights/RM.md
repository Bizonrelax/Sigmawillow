# Multiplicative Digit Weights Algorithm (BUC / PUS)

This section introduces an original structural framework for analyzing and evaluating numeric strings by mapping each individual digit to a multidimensional weight vector. Unlike standard positional notation, this approach defines a dynamic parameters vector based on the digital boundaries of the decimal system.

## 1. Base Multiplicative Weight (BUC)

Every non-zero digit \(x \in \{1, \dots, 9\}\) within a number has a fixed base weight vector \(W_{base}(x) = (a; b; c)\), where components are calculated using the squares, products, and differences relative to the system's extremes:
* \(a = x \times x = x^2\)
* \(b = x \times 9\)
* \(c = b - a\)

Digit `0` carries a zero weight. The base weights for all digits are defined as follows:
* \(W_{base}(1) = (1; 9; 8)\)
* \(W_{base}(2) = (4; 18; 14)\)
* \(W_{base}(3) = (9; 27; 18)\)
* \(W_{base}(4) = (16; 36; 20)\)
* \(W_{base}(5) = (25; 45; 20)\)
* \(W_{base}(6) = (36; 54; 18)\)
* \(W_{base}(7) = (49; 63; 14)\)
* \(W_{base}(8) = (64; 72; 8)\)
* \(W_{base}(9) = (81; 81; 0)\)

## 2. Ordinal Multiplicative Weight (PUS)

To evaluate the complete structural composition of a specific number, the base vector is expanded into a 4-dimensional ordinal vector \(W_{ord}(x) = (a; b; c; p)\), where \(p\) represents the specific position (index) of the digit within the sequence, counted from right to left (starting from 1).

### Structural Example
For the number \(458206\), the complete analytical profile of its components is mapped as follows:
* Digit `6` \(\rightarrow W_{ord}(6) = (36; 54; 18; 1)\)
* Digit `0` \(\rightarrow W_{ord}(0) = (0; 0; 0; 2)\)
* Digit `2` \(\rightarrow W_{ord}(2) = (4; 18; 14; 3)\)
* Digit `8` \(\rightarrow W_{ord}(8) = (64; 72; 8; 4)\)
* Digit `5` \(\rightarrow W_{ord}(5) = (25; 45; 20; 5)\)
* Digit `4` \(\rightarrow W_{ord}(4) = (16; 36; 20; 6)\)



___
___
___



# Алгоритм мультипликативных весов цифр (БУС / ПУС)

В данном разделе представлена оригинальная структурная концепция анализа числовых строк, основанная на сопоставлении каждой отдельной цифре многомерного вектора весов. В отличие от классической позиционной записи, этот подход определяет динамический вектор параметров, привязанный к цифровым границам десятичной системы.

## 1. Базовый мультипликативный вес (БУС)

Каждая значащая цифра \(x \in \{1, \dots, 9\}\) в числе обладает фиксированным базовым вектором весов \(W_{base}(x) = (a; b; c)\). Компоненты вектора рассчитываются через квадраты, произведения и разности относительно экстремумов системы:
* \(a = x \times x = x^2\)
* \(b = x \times 9\)
* \(c = b - a\)

Цифра `0` имеет нулевой вес. Базовые веса для всех цифр распределяются следующим образом:
* \(W_{base}(1) = (1; 9; 8)\)
* \(W_{base}(2) = (4; 18; 14)\)
* \(W_{base}(3) = (9; 27; 18)\)
* \(W_{base}(4) = (16; 36; 20)\)
* \(W_{base}(5) = (25; 45; 20)\)
* \(W_{base}(6) = (36; 54; 18)\)
* \(W_{base}(7) = (49; 63; 14)\)
* \(W_{base}(8) = (64; 72; 8)\)
* \(W_{base}(9) = (81; 81; 0)\)

## 2. Порядковый мультипликативный вес (ПУС)

Для полной оценки структуры конкретного числа базовый вектор расширяется до четырехмерного порядкового вектора \(W_{ord}(x) = (a; b; c; p)\), где \(p\) обозначает порядковое место (индекс) цифры в числовом ряду, отсчитываемое справа налево (начиная с 1).

### Пример структуры
Для числа \(458206\) полный аналитический профиль его компонентов выглядит следующим образом:
* У цифры `6` \(\rightarrow W_{ord}(6) = (36; 54; 18; 1)\)
* У цифры `0` \(\rightarrow W_{ord}(0) = (0; 0; 0; 2)\)
* У цифры `2` \(\rightarrow W_{ord}(2) = (4; 18; 14; 3)\)
* У цифры `8` \(\rightarrow W_{ord}(8) = (64; 72; 8; 4)\)
* У цифры `5` \(\rightarrow W_{ord}(5) = (25; 45; 20; 5)\)
* У цифры `4` \(\rightarrow W_{ord}(4) = (16; 36; 20; 6)\)
