from paper_rec.pdf import PdfEnricher


def test_extract_institutions_removes_numbering_and_project_footer() -> None:
    text = (
        "1 Fudan University 2Beijing Academy of Artificial Intelligence "
        "3Tsinghua University 4Renmin University of China\n"
        "SLIM-0.5B project page. Paper and code are available above."
    )

    assert PdfEnricher._extract_institutions(text) == [
        "Fudan University",
        "Beijing Academy of Artificial Intelligence",
        "Tsinghua University",
        "Renmin University of China",
    ]


def test_extract_institutions_keeps_wrapped_and_nonstandard_affiliations() -> None:
    text = (
        "1 HHCM, Istituto Italiano di Tecnologia, Genoa, Italy. "
        "2 DIBRIS, University of Genova, Genova, Italy. "
        "3 Human-Robot Interfaces and Interaction Lab, Istituto Italiano di Tec-\n"
        "nologia, Genova, Italy. "
        "4 Cognitive Robotics, TU Delft, 2628CD Delft, The Netherlands"
    )

    assert PdfEnricher._extract_institutions(text) == [
        "HHCM, Istituto Italiano di Tecnologia, Genoa, Italy.",
        "DIBRIS, University of Genova, Genova, Italy.",
        "Human-Robot Interfaces and Interaction Lab, Istituto Italiano di Tecnologia, Genova, Italy.",
        "Cognitive Robotics, TU Delft, 2628CD Delft, The Netherlands",
    ]
