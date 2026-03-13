import { useState, useEffect } from 'react'
import { Bar, Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend
)

interface ScoreBucket {
  bucket: string
  count: number
}

interface PassRate {
  task: string
  avg_score: number
  attempts: number
}

interface TimelineEntry {
  date: string
  submissions: number
}

interface GroupStats {
  group: string
  avg_score: number
  students: number
}

const LABS = ['lab-01', 'lab-02', 'lab-03', 'lab-04', 'lab-05', 'lab-06']

interface DashboardProps {
  token: string
}

export default function Dashboard({ token }: DashboardProps) {
  const [selectedLab, setSelectedLab] = useState<string>('lab-04')
  const [scores, setScores] = useState<ScoreBucket[]>([])
  const [passRates, setPassRates] = useState<PassRate[]>([])
  const [timeline, setTimeline] = useState<TimelineEntry[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)

    const headers = {
      Authorization: `Bearer ${token}`,
    }

    Promise.all([
      fetch(`/analytics/scores?lab=${selectedLab}`, { headers }),
      fetch(`/analytics/pass-rates?lab=${selectedLab}`, { headers }),
      fetch(`/analytics/timeline?lab=${selectedLab}`, { headers }),
    ])
      .then(async ([scoresRes, passRatesRes, timelineRes]) => {
        if (!scoresRes.ok) throw new Error(`Scores: HTTP ${scoresRes.status}`)
        if (!passRatesRes.ok)
          throw new Error(`Pass rates: HTTP ${passRatesRes.status}`)
        if (!timelineRes.ok)
          throw new Error(`Timeline: HTTP ${timelineRes.status}`)

        return Promise.all([
          scoresRes.json() as Promise<ScoreBucket[]>,
          passRatesRes.json() as Promise<PassRate[]>,
          timelineRes.json() as Promise<TimelineEntry[]>,
        ])
      })
      .then(([scoresData, passRatesData, timelineData]) => {
        setScores(scoresData)
        setPassRates(passRatesData)
        setTimeline(timelineData)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [selectedLab, token])

  const scoresData = {
    labels: scores.map((s) => s.bucket),
    datasets: [
      {
        label: 'Score Distribution',
        data: scores.map((s) => s.count),
        backgroundColor: 'rgba(54, 162, 235, 0.6)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1,
      },
    ],
  }

  const timelineData = {
    labels: timeline.map((t) => t.date),
    datasets: [
      {
        label: 'Submissions',
        data: timeline.map((t) => t.submissions),
        backgroundColor: 'rgba(75, 192, 192, 0.6)',
        borderColor: 'rgba(75, 192, 192, 1)',
        borderWidth: 2,
        tension: 0.3,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: 'Analytics Dashboard',
      },
    },
  }

  if (loading) {
    return (
      <div className="dashboard">
        <h2>Dashboard</h2>
        <p>Loading...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard">
        <h2>Dashboard</h2>
        <p className="error">Error: {error}</p>
        <p>Make sure to run the ETL pipeline sync first.</p>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>Analytics Dashboard</h2>
        <div className="lab-selector">
          <label htmlFor="lab-select">Select Lab: </label>
          <select
            id="lab-select"
            value={selectedLab}
            onChange={(e) => setSelectedLab(e.target.value)}
          >
            {LABS.map((lab) => (
              <option key={lab} value={lab}>
                {lab}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="charts-container">
        <div className="chart-card">
          <h3>Score Distribution ({selectedLab})</h3>
          <Bar data={scoresData} options={chartOptions} />
        </div>

        <div className="chart-card">
          <h3>Submissions Timeline ({selectedLab})</h3>
          <Line data={timelineData} options={chartOptions} />
        </div>

        <div className="chart-card">
          <h3>Pass Rates by Task ({selectedLab})</h3>
          {passRates.length > 0 ? (
            <table className="pass-rates-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Avg Score</th>
                  <th>Attempts</th>
                </tr>
              </thead>
              <tbody>
                {passRates.map((pr) => (
                  <tr key={pr.task}>
                    <td>{pr.task}</td>
                    <td>{pr.avg_score.toFixed(1)}%</td>
                    <td>{pr.attempts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No data available</p>
          )}
        </div>
      </div>
    </div>
  )
}
