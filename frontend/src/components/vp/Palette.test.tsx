import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Palette from './Palette'

describe('Palette', () => {
  it('renders Sources, Stages, Sinks sections', () => {
    render(<Palette />)
    expect(screen.getByText('Sources')).toBeInTheDocument()
    expect(screen.getByText('Stages')).toBeInTheDocument()
    expect(screen.getByText('Sinks')).toBeInTheDocument()
  })

  it('renders CameraSource, VideoFileSource, ImageFileSource', () => {
    render(<Palette />)
    expect(screen.getByText('CameraSource')).toBeInTheDocument()
    expect(screen.getByText('VideoFileSource')).toBeInTheDocument()
    expect(screen.getByText('ImageFileSource')).toBeInTheDocument()
  })

  it('renders Preprocess (CPU) and AprilTag Detect (CPU) stages', () => {
    render(<Palette />)
    expect(screen.getByText('Preprocess (CPU)')).toBeInTheDocument()
    expect(screen.getByText('AprilTag Detect (CPU)')).toBeInTheDocument()
  })

  it('renders StreamTap, SaveVideo, SaveImage, SVTVisionOutput sinks', () => {
    render(<Palette />)
    expect(screen.getByText('StreamTap')).toBeInTheDocument()
    expect(screen.getByText('SaveVideo')).toBeInTheDocument()
    expect(screen.getByText('SaveImage')).toBeInTheDocument()
    expect(screen.getByText('SVTVisionOutput')).toBeInTheDocument()
  })

  it('renders + New Stage button', () => {
    render(<Palette />)
    expect(screen.getByRole('button', { name: /New Stage/i })).toBeInTheDocument()
  })

  it('opens New Stage modal on click', async () => {
    const user = userEvent.setup()
    render(<Palette />)
    await user.click(screen.getByRole('button', { name: /New Stage/i }))
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Stage name/i)).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument()
  })
})
