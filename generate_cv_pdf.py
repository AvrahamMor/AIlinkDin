import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

CV_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page { margin: 25mm 20mm; size: A4; }
  body {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    color: #222;
    line-height: 1.5;
    margin: 0;
    padding: 0;
  }
  .header {
    border-bottom: 2px solid #2563eb;
    padding-bottom: 15px;
    margin-bottom: 20px;
  }
  h1 {
    font-size: 26px;
    margin: 0 0 5px 0;
    color: #0f172a;
    letter-spacing: -0.5px;
  }
  .sub-title {
    font-size: 15px;
    color: #2563eb;
    font-weight: 600;
    margin-bottom: 8px;
  }
  .contact-info {
    font-size: 12px;
    color: #64748b;
  }
  .contact-info span { margin-right: 15px; }
  .section-title {
    font-size: 14px;
    font-weight: 700;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin-top: 18px;
    margin-bottom: 10px;
  }
  p { font-size: 13px; margin: 0 0 8px 0; color: #334155; }
  .entry { margin-bottom: 12px; }
  .entry-header {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    font-weight: 700;
    color: #1e293b;
    margin-bottom: 2px;
  }
  .entry-sub {
    font-size: 12px;
    color: #64748b;
    margin-bottom: 5px;
  }
  ul {
    margin: 0 0 10px 18px;
    padding: 0;
    font-size: 12.5px;
    color: #334155;
  }
  li { margin-bottom: 4px; }
</style>
</head>
<body>

<div class="header">
  <h1>Avraham Natan</h1>
  <div class="sub-title">Software Engineering Student / Junior Developer</div>
  <div class="contact-info">
    <span>📧 avraham754@gmail.com</span>
    <span>📱 055-6630246</span>
    <span>📍 Safed, Israel (Northern District)</span>
    <span>💻 GitHub: github.com/AvrahamMor</span>
  </div>
</div>

<div class="section-title">Professional Summary</div>
<p>
Practical Software Engineering student in my second year at Tel Hai Technological College, with a solid foundation in Java, SQL, Python, and web development. Seeking a junior developer / student software engineering role in Northern Israel. Proven background in team coordination, fast learning, task prioritization, and structured workflows.
</p>

<div class="section-title">Education</div>
<div class="entry">
  <div class="entry-header">
    <span>Practical Software Engineering | Tel Hai Technological College</span>
    <span>2024 - Expected 2027</span>
  </div>
  <ul>
    <li><strong>Core Technical Stack:</strong> Java, SQL, PHP, JavaScript, HTML5, CSS3, Arduino.</li>
    <li><strong>Advanced Studies:</strong> Python, C, React, MongoDB, Linux, Data Structures & Algorithms.</li>
    <li>Integrating theoretical foundations with practical programming lab projects and software logic.</li>
  </ul>
</div>

<div class="section-title">Professional Experience</div>
<div class="entry">
  <div class="entry-header">
    <span>Restaurant Manager | "Bashert", Safed</span>
    <span>2023 - Present</span>
  </div>
  <div class="entry-sub">Safed, Israel</div>
  <ul>
    <li>Manage daily operations, staff coordination, inventory tracking, and logistics under high-pressure environments.</li>
    <li>Fostered strong teamwork, efficient problem-solving, and organized workflows.</li>
  </ul>
</div>

<div class="section-title">Technical Skills & Strengths</div>
<ul>
  <li><strong>Languages & Tech:</strong> Java, Python, SQL, JavaScript, React, PHP, C, HTML/CSS, MongoDB, Linux, Git.</li>
  <li><strong>Hardware & IoT:</strong> Integration of hardware and software (Arduino).</li>
  <li><strong>Strengths:</strong> Rapid self-learning of new frameworks, deep technical mindset, excellent task prioritization and team communication.</li>
</ul>

</body>
</html>
"""

async def generate_pdf():
    output_dir = Path("backend/storage/uploads")
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "Avraham_Natan_CV.pdf"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(CV_HTML)
        await page.pdf(path=str(pdf_path), format="A4", print_background=True)
        await browser.close()

    print(f"PDF generated successfully at: {pdf_path}")

if __name__ == "__main__":
    asyncio.run(generate_pdf())
