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
  Layers,
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

/** The house folder shape, drawn from a real project so it is recognisable. */
function Tree() {
  const rows: { indent: number; name: string; role: string }[] = [
    { indent: 0, name: 'ecom', role: 'project (base folder)' },
    { indent: 1, name: 'Apparel', role: 'category' },
    { indent: 2, name: 'Store 1', role: 'store' },
    { indent: 3, name: 'Denim Jacket', role: 'product' },
    { indent: 4, name: 'Denim Jacket - Static - Sale', role: 'request — the ad brief' },
  ]

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-bg-tertiary/40 p-3">
      <ul className="min-w-[22rem] space-y-1 font-mono text-[12px]">
        {rows.map((row) => (
          <li key={row.name} className="flex items-baseline gap-2 whitespace-nowrap">
            <span style={{ paddingLeft: `${row.indent * 1.25}rem` }} className="text-text-tertiary">
              {row.indent > 0 && '└─ '}
            </span>
            <span className="text-text-primary">{row.name}</span>
            <span className="text-text-tertiary">← {row.role}</span>
          </li>
        ))}
      </ul>
    </div>
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
          How to lay a project out, file work into it, ask an editor for a video,
          and move that work along the pipeline.
        </p>
      </div>

      {!isPlatformAdmin && (
        <Note>
          You are signed in as an editor. Steps marked <AdminOnly /> need a
          superadmin or sub-admin account — those buttons are hidden for you.
        </Note>
      )}

      <Section
        icon={Layers}
        title="Arrange a project"
        blurb="One shape, used everywhere: category, then store, then product, then the request. Get this right and the task list, the filters and the ad exports all line up on their own."
      >
        <p className="text-[13px] leading-relaxed text-text-secondary">
          The project is the base folder. Inside it you nest three levels of folders,
          and the request sits at the bottom:
        </p>

        <Tree />

        <Steps>
          <Step>
            <strong className="font-medium text-text-primary">Project</strong> — the
            base folder everything hangs off, e.g. <Ui>ecom</Ui>.
            <AdminOnly />
          </Step>
          <Step>
            <strong className="font-medium text-text-primary">Category</strong> — the
            niche, e.g. <Ui>Phones</Ui> or <Ui>Consumer electronics</Ui>. This is the
            level you will most often filter the task list by.
          </Step>
          <Step>
            <strong className="font-medium text-text-primary">Store</strong> — the
            storefront selling in that category, e.g. <Ui>Store 1</Ui>. Keep it even
            when there is only one store today, so adding a second later does not
            mean re-filing everything.
          </Step>
          <Step>
            <strong className="font-medium text-text-primary">Product</strong> — the
            item the ad is for, e.g. <Ui>Denim Jacket</Ui>. This is the last folder you
            make; requests go inside it.
          </Step>
          <Step>
            <strong className="font-medium text-text-primary">Request</strong> — the
            ad brief itself, e.g. <Ui>Denim Jacket - Static - Sale</Ui>. One request per
            ad you want made. It is not a folder — you create it with{' '}
            <Ui>New Request</Ui> and the videos an editor submits against it land
            underneath.
            <AdminOnly />
          </Step>
        </Steps>

        <Note>
          The full path is written as{' '}
          <Ui>ecom/Apparel/Store 1/Denim Jacket</Ui> and appears in the{' '}
          <Ui>Category</Ui> column on the Tasks page. Click it to filter the whole
          list down to that branch, then use the breadcrumb to come back up. It is
          derived from the folder, never typed, so renaming a folder moves every
          request and video beneath it at once.
        </Note>
      </Section>

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
            menu and choose <Ui>New Subfolder</Ui>. This is how you build category →
            store → product: make the category at the root, then a subfolder under
            it, then one more. The same menu has <Ui>Rename</Ui>.
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
            list, so name it the way you want the finished work labelled. The house
            pattern is product, format, then angle:{' '}
            <Ui>Denim Jacket - Static - Sale</Ui>.
          </Step>
          <Step>
            Add <Ui>Instructions</Ui> if the editor needs a brief. Editors read this
            before they upload.
          </Step>
          <Step>
            Choose the <Ui>Project</Ui> and the folder this request is filed under.
            Pick the <strong className="font-medium text-text-primary">product</strong>{' '}
            folder — that is what gives the finished video its category and store. A
            project is required; leaving the folder blank files the request at the
            project root, where it has no category to filter by.
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
