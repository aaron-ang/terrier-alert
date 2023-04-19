from datetime import datetime


class Course:
    _bin_prefix = ("https://www.bu.edu/link/bin/uiscgi_studentlink.pl/1?ModuleName="
                   "univschr.pl&SearchOptionDesc=Class+Number&SearchOptionCd=S")
    _reg_prefix = ("https://www.bu.edu/link/bin/uiscgi_studentlink.pl/1?ModuleName="
                   "reg%2Fadd%2Fbrowse_schedule.pl&SearchOptionDesc=Class+Number&SearchOptionCd=S")
    REFRESH_TIME_HOURS = 24

    @staticmethod
    def get_semester():
        return "Fall" if 4 <= datetime.now().month < 10 else "Spring"

    @classmethod
    def get_year(cls):
        return datetime.now().year + 1 if (cls.get_semester() == "Spring" and 10 <=
                                           datetime.now().month <= 12) else datetime.now().year

    def __init__(self, full_course: str):
        college, dep_num, section = full_course.split()
        department, number = dep_num[:2], dep_num[2:]
        year, semester = self.get_year(), self.get_semester()
        
        self.year = year + 1 if semester == "Fall" else year
        self.sem_code = 3 if semester == "Fall" else 4
        self.college = college.upper()
        self.department = department.upper()
        self.number = number
        self.section = section.upper()

        self.formatted_params = (f"&KeySem={self.year}{self.sem_code}=&College={self.college}"
                                 f"&Dept={self.department}&Course={self.number}&Section={self.section}")

        self.bin_url = self._bin_prefix + self.formatted_params
        self.reg_url = self._reg_prefix + self.formatted_params

    def __str__(self):
        return f"{self.college} {self.department}{self.number} {self.section}"
