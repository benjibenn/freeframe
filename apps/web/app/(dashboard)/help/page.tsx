'use client'

/**
 * The admin one-pager: folders, requests, task status.
 *
 * Static on purpose — no API calls, so it renders even when something else is
 * broken and it is the page you can still reach to find out what to do. The one
 * live bit is the viewer's own role, used to tell them up front which of the
 * steps below they will actually see buttons for.
 */

import * as React from 'react'
import Link from 'next/link'
import {
  FolderPlus,
  FileText,
  ListChecks,
  ShieldCheck,
  Info,
} from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { usePageTitle } from '@/hooks/use-page-title'
import { cn } from '@/lib/utils'

/** A step that only superadmins and sub-admins can carry out. */
function AdminOnly() {
  return (
    <span className="ml-1.5 inline-flex items-center gap-1 rounded-full border border-border px-1.5 py-px align-middle text-[10px] font-medium text-text-tertiary">
      <ShieldCheck className="h-2.5 w-2.5" />
      Admin
    </span>
  )
}

/** A literal button or menu label as it appears in the app. */
function Ui({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded border border-border bg-bg-tertiary px-1.5 py-px text-[12px] font-medium text-text-primary">
      {children}
    </span>
  )
}

function Section({
  icon: Icon,
  title,
  blurb,
  children,
}: {
  icon: React.ElementType
  title: string
  blurb: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-border bg-bg-secondary p-5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-text-primary">{title}</h2>
          <p className="mt-0.5 text-[13px] text-text-secondary">{blurb}</p>
        </div>
      </div>
      <div className="mt-4 space-y-3 pl-0 sm:pl-11">{children}</div>
    </section>
  )
}

function Steps({ children }: { children: React.ReactNode }) {
  return (
    <ol className="space-y-2 text-[13px] leading-relaxed text-text-secondary [counter-reset:step]">
      {children}
    </ol>
  )
}

function Step({ children }: { children: React.ReactNode }) {
  return (
    <li
      className={cn(
        'relative pl-7 [counter-increment:step]',
        // The number sits in the gutter so wrapped lines stay flush.
        'before:absolute before:left-0 before:top-0 before:flex before:h-5 before:w-5',
        'before:items-center before:justify-center before:rounded-full before:bg-bg-tertiary',
        'before:text-[11px] before:font-semibold before:text-text-secondary',
        'before:content-[counter(step)]',
      )}
    >
      {children}
    </li>
  )
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex gap-2 rounded-lg border border-border bg-bg-tertiary/40 px-3 py-2 text-[12px] leading-relaxed text-text-tertiary">
      <Info className="mt-px h-3.5 w-3.5 shrink-0" />
      <span>{children}</span>
    </p>
  )
}

export default function HelpPage() {
  usePageTitle('Guide')
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)

  return (
    <div className="max-w-3xl space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Admin guide</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Three things you will do most: file work into folders, ask an editor for a
          video, and move that work along the pipeline.
        </p>
      </div>

      {!isPlatformAdmin && (
        <Note>
          You are signed in as an editor. Steps marked <AdminOnly /> need a
          superadmin or sub-admin account — those buttons are hidden for you.
        </Note>
      )}

      <Section
        icon={FolderPlus}
        title="Create a folder"
        blurb="Folders live inside a project and nest as deep as you need. They are the filing tree everything else points at."
      >
        <Steps>
          <Step>
            Open <Ui>Projects</Ui> in the sidebar and click the project you want to
            file into.
          </Step>
          <Step>
            Click <Ui>New Folder</Ui> in the toolbar, type a name, then{' '}
            <Ui>Create</Ui>. The folder is created inside whichever folder you are
            currently viewing — check the breadcrumb first if you want it at the
            project root.
          </Step>
          <Step>
            To nest one level deeper, hover a folder in the left-hand tree, open its{' '}
            menu and choose <Ui>New Subfolder</Ui>. The same menu has{' '}
            <Ui>Rename</Ui>.
          </Step>
          <Step>
            Drag videos or whole folders onto another folder in the tree to move
            them. Dropping onto the project name at the top moves an item back to
            the root.
          </Step>
        </Steps>
        <Note>
          Two folders under the same parent cannot share a name. Deleted folders go
          to <Ui>Recently Deleted</Ui> at the bottom of the tree rather than
          disappearing.
        </Note>
      </Section>

      <Section
        icon={FileText}
        title="Create a request"
        blurb="A request is one link you share with many editors. Each person who accepts it gets their own private space to upload into, and only you see them all."
      >
        <Steps>
          <Step>
            From <Ui>Projects</Ui>, click <Ui>New</Ui> then <Ui>New Request</Ui>.
            <AdminOnly />
            <br />
            Already inside the right folder? Use the <Ui>New Request</Ui> button in
            that project's toolbar and the filing location is filled in for you.
          </Step>
          <Step>
            Give it a <Ui>Request name</Ui>. This is what everyone sees in the task
            list, so name it the way you want the finished work labelled.
          </Step>
          <Step>
            Add <Ui>Instructions</Ui> if the editor needs a brief. Editors read this
            before they upload.
          </Step>
          <Step>
            Choose the <Ui>Project</Ui> and, optionally, the folder this request is
            filed under. A project is required. The folder is the source of truth
            for the request's path, so renaming the folder later carries the request
            with it.
          </Step>
          <Step>
            Click <Ui>Create request</Ui>. You land on the request page — click{' '}
            <Ui>Copy submission link</Ui> and send that link to your editors.
          </Step>
        </Steps>
        <Note>
          A request appears in <Ui>Tasks</Ui> the moment you create it, before
          anything is uploaded, so an empty brief is visible rather than forgotten.
          Closing a request stops the link accepting new uploads; work already
          submitted is kept.
        </Note>
      </Section>

      <Section
        icon={ListChecks}
        title="Update task status"
        blurb="Every request carries a stage. Stages are the columns of the pipeline and you define them yourself."
      >
        <Steps>
          <Step>
            Open <Ui>Tasks</Ui> in the sidebar.
          </Step>
          <Step>
            In the <Ui>To-do</Ui> view, use the <Ui>Status</Ui> dropdown on a row and
            pick a stage. It saves immediately — there is no separate save button.
          </Step>
          <Step>
            Prefer a board? Switch to <Ui>Pipeline</Ui> and drag a card into another
            column. Same result, same stages.
          </Step>
          <Step>
            Set whose desk a brief sits on with the <Ui>Assigned to</Ui> dropdown on
            the row.
            <AdminOnly />
          </Step>
          <Step>
            To change the stages themselves, click <Ui>Manage stages</Ui>.
            <AdminOnly /> There you can add a stage with a name and colour, rename
            one inline, reorder with the arrows, and star a stage to make it the
            landing stage for new uploads.
          </Step>
        </Steps>
        <Note>
          Deleting a stage never deletes work — anything sitting in it loses its
          stage and shows under the <Ui>Unassigned</Ui> filter chip. Requests and individual
          videos draw from the same set of stages, so a stage name means the same
          thing wherever you see it.
        </Note>
        <Note>
          Editors do not get a <Ui>Tasks</Ui> link in the sidebar, but they can open{' '}
          <Link href="/tasks" className="text-accent hover:underline">
            /tasks
          </Link>{' '}
          directly to see and move the briefs assigned to them.
        </Note>
      </Section>
    </div>
  )
}
