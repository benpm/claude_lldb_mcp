// Test program for variable examination
#include <iostream>
#include <string>
#include <vector>

struct Point {
    int x;
    int y;
};

void process_data(int count, const std::string& name) {
    Point pt = {10, 20};  // Line 12
    std::vector<int> numbers = {1, 2, 3, 4, 5};  // Line 13

    int local_var = count * 2;  // Line 15 - good breakpoint location

    std::cout << "Processing " << name << " with count " << count << std::endl;
    std::cout << "Point: (" << pt.x << ", " << pt.y << ")" << std::endl;
    std::cout << "Local var: " << local_var << std::endl;
}

int main() {
    std::string test_name = "TestData";  // Line 23
    int test_count = 42;  // Line 24

    process_data(test_count, test_name);  // Line 26

    return 0;
}
